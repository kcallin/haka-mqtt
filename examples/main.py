from __future__ import print_function
import argparse
import logging
import socket
import sys

from haka_mqtt.poll import MqttPollClientProperties, MqttPollClient
from mqtt_codec.packet import MqttTopic

TOPIC = 'bubbles'


class ExampleMqttClient(MqttPollClient):
    def __init__(self, endpoint):
        properties = MqttPollClientProperties()
        properties.client_id = 'bobby'
        properties.keepalive_period = 10
        properties.ssl = True
        properties.host, properties.port = endpoint
        properties.address_family = socket.AF_UNSPEC

        super(type(self), self).__init__(properties)

        self.__req_queue = set()
        self.__ack_queue = set()

        self.__pub_period = 5.
        self.__pub_deadline = None
        self.__reconnect_period = 10.
        self.__reconnect_deadline = None

    def on_disconnect(self, reactor):
        assert self.__reconnect_deadline is None
        self.__reconnect_deadline = self._scheduler.add(self.__reconnect_period, self.on_reconnect_timeout)
        self.__pub_deadline.cancel()
        self.__pub_deadline = None

    def on_connect_fail(self, reactor):
        assert self.__reconnect_deadline is None
        self.__reconnect_deadline = self._scheduler.add(self.__reconnect_period, self.on_reconnect_timeout)
        self.__pub_deadline.cancel()
        self.__pub_deadline = None

    def on_reconnect_timeout(self):
        self.__reconnect_deadline.cancel()
        self.__reconnect_deadline = None

        self.start()

    def on_suback(self, reactor, p):
        """

        Parameters
        ----------
        reactor: Reactor
        p: MqttSuback
        """
        self.__ack_queue.add(p.packet_id)

    def on_puback(self, reactor, p):
        """

        Parameters
        ----------
        reactor: Reactor
        p: mqtt_codec.packet.MqttPuback
        """
        self.__ack_queue.add(p.packet_id)

    def on_pub_timeout(self):
        if len(self.__req_queue) == len(self.__ack_queue):
            publish = self.publish(TOPIC, str(len(self.__req_queue)), 1)
            self.__req_queue.add(publish.packet_id)

        self.__pub_deadline = self._scheduler.add(self.__pub_period, self.on_pub_timeout)

    def on_connack(self, reactor, p):
        """

        Parameters
        ----------
        reactor: Reactor
        p: MqttConnack
        """
        sub_ticket = self.subscribe([
            MqttTopic(TOPIC, 1),
        ])
        self.__req_queue.add(sub_ticket.packet_id)

    def on_publish(self, reactor, p):
        """

        Parameters
        ----------
        reactor: Reactor
        p: MqttPuback
        """
        pass

    def start(self):
        self.__pub_deadline = self._scheduler.add(self.__pub_period, self.on_pub_timeout)
        super(type(self), self).start()


def argparse_endpoint(s):
    """

    Parameters
    ----------
    s: str

    Returns
    -------
    (str, int)
        hostname, port tuple.
    """
    words = s.split(':')
    if len(words) != 2:
        raise argparse.ArgumentTypeError('Format of endpoint must be hostname:port.')
    host, port = words

    try:
        port = int(port)
        if not 1 <= port <= 2**16-1:
            raise argparse.ArgumentTypeError('Port must be in the range 1 <= port <= 65535.')
    except ValueError:
        raise argparse.ArgumentTypeError('Format of endpoint must be hostname:port.')

    return host, port


def create_parser():
    """

    Returns
    -------
    argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("endpoint", type=argparse_endpoint)

    return parser


def main(args=sys.argv[1:]):
    logging.basicConfig(format='%(asctime)-15s %(name)s %(levelname)s %(message)s', level=logging.DEBUG, stream=sys.stdout)

    #
    # 1883 : MQTT, unencrypted
    # 8883 : MQTT, encrypted
    # 8884 : MQTT, encrypted, client certificate required
    # 8080 : MQTT over WebSockets, unencrypted
    # 8081 : MQTT over WebSockets, encrypted
    #
    # from https://test.mosquitto.org/ (2018-09-19)
    #

    # addr = ('2001:41d0:a:3a10::1', 8883, 0, 0)
    # sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    # sock.connect(addr)

    parser = create_parser()
    ns = parser.parse_args(args)

    client = ExampleMqttClient(ns.endpoint)
    client.start()

    while True:
        client.poll(5.)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))