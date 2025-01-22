import json
import logging
import polyline
import re
import time
import uuid
import yaml

from datetime import datetime
from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import ParseDict
from mako.template import Template
from shapely import LineString
from shapely.ops import transform
from pyproj import CRS, Transformer
from urllib.parse import urlparse

from .mqtt import GtfsRealtimeServiceAlertPublisher
from .otpclient import OtpClient

class OtpGtfsMatcher:

    def __init__(self, otp_url: str, template_filename: str):
        self._otp_client = OtpClient(otp_url)
        
        with open(template_filename, 'r', encoding='utf-8') as template_file:
            templates = yaml.safe_load(template_file)
            self._templates = templates['templates']

    def match(self, input_filename, output_filename, mqtt_uri):
        
        # load incident input GeoJSON file
        with open(input_filename, 'r') as geojson_file:
            geojson = json.loads(geojson_file.read())

        # load active patterns for the current operation day
        otp_patterns = self._otp_client.load_active_pattern(
            datetime.now().strftime('%Y-%m-%d')
        )

        # iterate through all incidents found
        alerts = dict()
        for incident in geojson['features']:
            if self._any_template_available(incident):

                if incident['geometry']['type'] == 'LineString':
                    incident_shape = LineString(incident['geometry']['coordinates'])
 
                incident_shape = transform(Transformer.from_crs(CRS('EPSG:4326'), CRS('EPSG:3857'), always_xy=True).transform, incident_shape)

                # check for patterns matching this incident
                affected_routes = dict()
                for pattern in otp_patterns:
                    if self._test_pattern_match(pattern, incident_shape):
                        if pattern['route']['gtfsId'] not in affected_routes.keys():
                            affected_routes[pattern['route']['gtfsId']] = pattern['route']

                # if there's at least one line affected ...
                if len(affected_routes) > 0:
                    for template in self._templates:
                        if self._template_available(template, incident):
                            template_data = {
                                'startLocationName': incident['properties']['from'],
                                'endLocationName': incident['properties']['to'],
                                'affectedLines': self._natural_sort(list(affected_routes.values()), 'shortName')
                            }
                            
                            alert_id, alert_entity = self._create_service_alert(template, incident, **template_data)
                            alerts[alert_id] = alert_entity

                            # log incident for debugging purposes
                            logging.info('Alert ID: ' + alert_id)
                            logging.info('Alert Data: ' + str(alert_entity))

                            # first template has matched
                            # do not create multiple alerts
                            # for the same incident
                            break

        # create desired output
        logging.info(f"found {len(alerts)} incidents total")
        if mqtt_uri is not None:
            logging.info("publishing to MQTT ...")

            mqtt_uri = urlparse(mqtt_uri)

            mqtt_params = mqtt_uri.netloc.split('@')
            mqtt_topic = mqtt_uri.path

            if len(mqtt_params) == 1:
                mqtt_username, mqtt_password = None, None
                mqtt_host, mqtt_port = mqtt_params[0].split(':')
            elif len(mqtt_params) == 2:
                mqtt_username, mqtt_password = mqtt_params[0].split(':')
                mqtt_host, mqtt_port = mqtt_params[1].split(':')

            mqtt_publisher = GtfsRealtimeServiceAlertPublisher(
                host=mqtt_host,
                port=mqtt_port,
                username=mqtt_username,
                password=mqtt_password,
                topic=mqtt_topic
            )

            mqtt_publisher.start()

            for alert_id, alert_entity in alerts.items():
                mqtt_publisher.publish(alert_id, alert_entity)

            mqtt_publisher.stop()
        else:
            logging.info("writing output file ...")

            feed_message = dict()
            feed_message['header'] = {
                'gtfs_realtime_version': '2.0',
                'incrementality': 'FULL_DATASET',
                'timestamp': int(time.time())
            } 

            feed_message['entity'] = list()
            for alert_id, alert_entity in alerts.items():
                feed_message['entity'].append({
                    'id': alert_id,
                    'alert': alert_entity
                })

            if output_filename.endswith('.json'):
                with open(output_filename, 'wb') as output_file:
                    output_file.write(json.dumps(feed_message, indent=2, ensure_ascii=False).encode('utf-8'))
            elif output_filename.endswith('.pbf'):
                with open(output_filename, 'wb') as output_file:
                    pbf_object = gtfs_realtime_pb2.FeedMessage()
                    ParseDict(feed_message, pbf_object)

                    output_file.write(pbf_object.SerializeToString())

    def _any_template_available(self, incident: dict) -> bool:
        if incident['properties']['events'] is None:
            return False

        for template in self._templates:
             if self._template_available(template, incident):
                 return True

        return False
    
    def _template_available(self, template: dict, incident: dict) -> bool:
        incident_codes = [e['code'] for e in incident['properties']['events']]

        available = False
        for template_condition in template['conditions']:
            if template_condition['code'] in incident_codes:
                available = True
            
            if 'or' in template_condition:
                for or_code in template_condition['or']:
                    available = available or or_code in incident_codes 
        
            if 'delay' in incident['properties'] and 'delay' in template_condition and incident['properties']['delay'] is not None and incident['properties']['delay'] < template_condition['delay']:
                available = False
        
        return available
    
    def _test_pattern_match(self, pattern: dict, incident_shape: any) -> bool:
        pattern_coordinates = polyline.decode(
            pattern['patternGeometry']['points']
        )

        pattern_shape = LineString([c[::-1] for c in pattern_coordinates])
        pattern_shape = transform(Transformer.from_crs(CRS('EPSG:4326'), CRS('EPSG:3857'), always_xy=True).transform, pattern_shape)

        if type(incident_shape) == LineString:

            # Note: Intersection length should be a minimum of 40m with buffer size of 5m to avoid 
            # incident alerts for lines which are only crossing an incident, as they might not be affected.
            # Be aware, that an intersection could happen in an angle of 90° (a normal crossing) but
            # also can happen in an angle different than 90 degrees (e.g. a street located below or above another street).
            # The buffer transforms the incident shape into a polygon which leads to a longer intersection at all!
            
            incident_shape = incident_shape.buffer(5.0)
            intersection = pattern_shape.intersection(incident_shape)

            if intersection.length >= 40.0:
                return True
        
        return False
    
    def _create_translated_string(self, template: dict, type: str, **data) -> dict:
        translated_string = dict()
        translated_string['translation'] = list()

        if type in template:
            for lang, text in template[type].items():
                tmpl = Template(text)
                translated_string['translation'].append({
                    'language': lang,
                    'text': tmpl.render(
                        **data, 
                        natural_sort=self.__t_natural_sort,
                        extract_property=self.__t_extract_property
                    ).replace('\n', '')
                })

        return translated_string
    
    def _create_service_alert(self, template: dict, incident: dict, **data) -> tuple:
        
        root_uuid = uuid.UUID('0715e0ca-0427-49ce-b3c8-5f83b400d00b')
        alert_id = str(uuid.uuid5(namespace=root_uuid, name=incident['properties']['id']))
        
        alert_entity = {
            'cause': template['cause'],
            'effect': template['effect']
        }

        alert_entity['informed_entity'] = list()
        for line in data['affectedLines']:
            alert_entity['informed_entity'].append({
                'route_id': line['gtfsId']
            })

        alert_entity['url'] = self._create_translated_string(template, 'url', **{'id': alert_id})
        alert_entity['header_text'] = self._create_translated_string(template, 'header', **data)
        alert_entity['description_text'] = self._create_translated_string(template, 'description', **data)

        return alert_id, alert_entity

    def _natural_sort(self, l, property=None):
        convert = lambda text: int(text) if text.isdigit() else text.lower()
        if property is not None:
            alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key[property])]
        else:
            alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]

        return sorted(l, key=alphanum_key)

    def __t_natural_sort(self, l):    
        return self._natural_sort(l, None)
    
    def __t_extract_property(self, l, property):
        result = [x[property] for x in l]

        return result
