"""Basic client that connects to test.mosquitto.org, subscribes
to a topic, publishes to that topic, awaits notification of
publish on that topic, then cleanly disconnects."""

# Standard python Packages
import logging

# 3rd-Party Packages
from haka_mqtt.frontends.poll import (
    MqttPollClientProperties,
    BlockingMqttClient
)
from haka_mqtt.reactor import ACTIVE_STATES
from mqtt_codec.packet import MqttTopic

LOG_FMT='%(asctime)s %(name)s %(levelname)s %(message)s'
logging.basicConfig(format=LOG_FMT, level=logging.INFO)

properties = MqttPollClientProperties()
properties.host = 'test.mosquitto.org'
properties.port = 1883
properties.ssl = False

TOPIC = 'haka'

c = BlockingMqttClient(properties)
c.start()
sub_ticket = c.subscribe([MqttTopic(TOPIC, 1)])
c.on_suback = lambda c, suback: c.publish(TOPIC, 'payload', 1)
c.on_publish = lambda c, publish: c.stop()

while c.state in ACTIVE_STATES:
    c.poll(5.)
