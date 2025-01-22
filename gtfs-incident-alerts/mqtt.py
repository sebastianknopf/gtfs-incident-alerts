import json
import logging
import os
import time

from appdirs import site_data_dir
from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import ParseDict
from paho.mqtt import client
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from .__version__ import __version__

class GtfsRealtimeServiceAlertPublisher:

    def __init__(self, host, port, username, password, topic, expiration):

        self._expiration = expiration

        # connecto to MQTT broker as defined in config
        topic = topic.replace('+', '_')
        topic = topic.replace('#', '_')
        topic = topic.replace('$', '_')
        
        self._topic = topic

        self._mqtt = client.Client(client.CallbackAPIVersion.VERSION2, protocol=client.MQTTv5)

        if username is not None and password is not None:
            self._mqtt.username_pw_set(username=username, password=password)

        self._mqtt.connect(host, int(port))
    
    def __enter__(self) -> None:
        self._mqtt.loop_start()

        return self

    def __exit__(self, exception_type, exception_value, exception_traceback) -> None:
        self._mqtt.loop_stop()
        self._mqtt.disconnect()

    def publish(self, alerts: dict) -> None:
        mqtt_mirror_dir = site_data_dir(appname='gtfs-incident-alerts', appauthor='skc', version=__version__)
        if not os.path.exists(mqtt_mirror_dir):
            os.makedirs(mqtt_mirror_dir)
            
        mqtt_mirror_filename = os.path.join(mqtt_mirror_dir, 'mqtt.mirror')
        if not os.path.exists(mqtt_mirror_filename):
            with open(mqtt_mirror_filename, 'w') as mqtt_mirror_file:
                mqtt_mirror_file.write('{}')

        logging.info(f"MQTT Mirror: Filename is {mqtt_mirror_filename}")

        with open(mqtt_mirror_filename, 'r+') as mqtt_mirror_file:

            # read MQTT mirror
            try:
                mqtt_mirror = json.loads(mqtt_mirror_file.read())
            except json.decoder.JSONDecodeError:
                mqtt_mirror = dict()

            # publish all active alerts
            # add them to MQTT mirror, if not already present
            for alert_id, alert_entity in alerts.items():
                if alert_id not in mqtt_mirror:
                    mqtt_mirror[alert_id] = alert_entity
                    
                    logging.info(f"MQTT Mirror: Alert {alert_id} added successfully")

                self._publish(alert_id, alert_entity)

            # run over mirror and find all alerts which are not present anymore
            # publish them as deleted entity and delete them form mirror
            deleted_alerts_ids = list()
            for alert_id, alert_entity in mqtt_mirror.items():
                if alert_id not in alerts:
                    deleted_alerts_ids.append(alert_id)
                    logging.info(f"MQTT Mirror: Alert {alert_id} removed successfully")

                    self._publish(alert_id, alert_entity, True)
            
            for deleted_alert_id in deleted_alerts_ids:
                del mqtt_mirror[deleted_alert_id]

            # write back MQTT mirror
            mqtt_mirror_file.truncate(0)
            mqtt_mirror_file.seek(0)
            mqtt_mirror_file.write(json.dumps(mqtt_mirror))

    def _publish(self, alert_id: str, alert_entity: dict, is_deleted: bool = False) -> None:

        # generate MQTT topic from placeholders
        topic = self._topic
        topic = topic.replace('[alertId]', alert_id)

        # generate feed message containing a single alert
        feed_message = dict()
        feed_message['header'] = {
            'gtfs_realtime_version': '2.0',
            'incrementality': 'DIFFERENTIAL',
            'timestamp': int(time.time())
        }

        feed_message['entity'] = list()

        # publish message
        if is_deleted:
            # delete message from MQTT
            feed_message['entity'].append({
                'id': alert_id,
                'alert': alert_entity,
                'is_deleted': True
            })
        else:
            # convert to PBF message and publish
            feed_message['entity'].append({
                'id': alert_id,
                'alert': alert_entity
            })
        
        logging.info(f"MQTT: Published GTFS-RT feed message f{feed_message}")
            
        pbf_object = gtfs_realtime_pb2.FeedMessage()
        ParseDict(feed_message, pbf_object)

        properties = Properties(PacketTypes.PUBLISH)
        properties.MessageExpiryInterval = self._expiration

        self._mqtt.publish(topic, pbf_object.SerializeToString(), 0, True, properties) 