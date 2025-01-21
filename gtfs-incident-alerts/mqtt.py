import time
import yaml

from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import ParseDict
from paho.mqtt import client

class GtfsRealtimeServiceAlertPublisher:

    def __init__(self, host, port, username, password, topic):

        # connecto to MQTT broker as defined in config
        topic = topic.replace('+', '_')
        topic = topic.replace('#', '_')
        topic = topic.replace('$', '_')
        
        self._topic = topic

        self._mqtt = client.Client(client.CallbackAPIVersion.VERSION2, protocol=client.MQTTv5)

        if username is not None and password is not None:
            self._mqtt.username_pw_set(username=username, password=password)

        self._mqtt.connect(host, int(port))

    def start(self) -> None:
        self._mqtt.loop_start()

    def stop(self) -> None:
        self._mqtt.loop_stop()

    def publish(self, alert_id: str, alert_entity: dict) -> None:

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

        feed_message['entity'].append({
            'id': alert_id,
            'alert': alert_entity
        })
        
        # publish message
        if 'is_deleted' in feed_message['entity'][0]:
            # delete message from MQTT
            self._mqtt.publish(topic, None, 1, True)
        else:
            # convert to PBF message and publish
            pbf_object = gtfs_realtime_pb2.FeedMessage()
            ParseDict(feed_message, pbf_object)

            self._mqtt.publish(topic, pbf_object.SerializeToString(), 0, True) 