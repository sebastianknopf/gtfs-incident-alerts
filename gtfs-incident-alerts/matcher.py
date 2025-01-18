import json
import logging
import polyline
import re
import time
import yaml

from datetime import datetime
from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import ParseDict
from mako.template import Template
from shapely import LineString

from .otpclient import OtpClient

class OtpGtfsMatcher:

    def __init__(self, otp_url: str, template_filename: str):
        self._otp_client = OtpClient(otp_url)
        
        with open(template_filename, 'r', encoding='utf-8') as template_file:
            templates = yaml.safe_load(template_file)
            self._templates = templates['templates']

    def match(self, input_filename, output_filename):
        with open(input_filename, 'r') as geojson_file:
            geojson = json.loads(geojson_file.read())

        otp_patterns = self._otp_client.load_active_pattern(
            datetime.now().strftime('%Y-%m-%d')
        )

        feed_message = dict()
        feed_message['header'] = {
            'gtfs_realtime_version': '2.0',
            'incrementality': 'FULL_DATASET',
            'timestamp': int(time.time())
        } 

        feed_message['entity'] = list()

        for incident in geojson['features']:
            if self._any_template_available(incident):

                affected_routes = dict()
                affected_data = False

                for pattern in otp_patterns:
                    if self._test_pattern_match(pattern, incident):
                        affected_data = True

                        if pattern['route']['gtfsId'] not in affected_routes.keys():
                            affected_routes[pattern['route']['gtfsId']] = pattern['route']

                if affected_data:
                    for template in self._templates:
                        if self._template_available(template, incident):
                            template_data = {
                                'startLocationName': incident['properties']['from'],
                                'endLocationName': incident['properties']['to'],
                                'affectedLineIds': list(affected_routes.keys()),
                                'affectedLineNames': self._natural_sort([r['shortName'] for r in affected_routes.values()])
                            }
                            
                            alert_id, alert_entity = self._create_service_alert(template, incident, **template_data)

                            feed_message['entity'].append({
                                'id': alert_id,
                                'alert': alert_entity
                            })

                            logging.info(str(alert_entity))

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
        if not all(c in incident_codes for c in template['codes']):
            return False
        
        if 'delay' in incident['properties'] and (incident['properties']['delay'] < template['delay_min'] or incident['properties']['delay'] > template['delay_max']):
            return False
        
        return True
    
    def _test_pattern_match(self, pattern: dict, incident: dict) -> bool:
        pattern_coordinates = polyline.decode(
            pattern['patternGeometry']['points']
        )

        pattern_shape = LineString([c[::-1] for c in pattern_coordinates])
        
        if incident['geometry']['type'] == 'LineString':
            incident_shape = LineString(incident['geometry']['coordinates'])

            distance = pattern_shape.distance(incident_shape)
            if distance == 0.0:
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
                    'text': tmpl.render(**data).replace('\n', '')
                })

        return translated_string
    
    def _create_service_alert(self, template: dict, incident: dict, **data) -> tuple:
        alert_id = incident['properties']['id']
        
        alert_entity = {
            'cause': template['cause'],
            'effect': template['effect']
        }

        alert_entity['url'] = self._create_translated_string(template, 'url', **{'id': alert_id})
        alert_entity['header_text'] = self._create_translated_string(template, 'header', **data)
        alert_entity['description_text'] = self._create_translated_string(template, 'description', **data)

        return alert_id, alert_entity

    def _natural_sort(self, l):    
        convert = lambda text: int(text) if text.isdigit() else text.lower()
        alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]

        return sorted(l, key=alphanum_key)
