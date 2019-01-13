#!/bin/env python
from __future__ import print_function
import logging
import socket
import sys
from argparse import ArgumentParser

from haka_mqtt.frontends.poll import MqttPollClientProperties, MqttPollClient
from haka_mqtt.reactor import ACTIVE_STATES
from mqtt_codec.packet import MqttTopic


class MqttSubClient(MqttPollClient):
    """
    Parameters
    ----------
    endpoint: tuple of str and int
        Tuple contains the hostname and port to connect to.
    topics: list of MqttTopic
    """
    def __init__(self, endpoint, topics, clientid=None, keepalive_period=0, ssl=False):
        properties = MqttPollClientProperties()
        properties.ssl = ssl
        properties.client_id = clientid
        properties.host, properties.port = endpoint
        properties.address_family = socket.AF_UNSPEC
        properties.keepalive_period = keepalive_period
        properties.recv_idle_ping_period = 5*60*1000
        properties.recv_idle_abort_period = 7*60*1000

        MqttPollClient.__init__(self, properties)

        self.__topics = topics
        self.__req_queue = set()
        self.__ack_queue = set()

        self.__reconnect_period = 10.
        self.__reconnect_deadline = None

    def on_disconnect(self, reactor):
        """

        Parameters
        ----------
        reactor: Reactor
        """

        assert self.__reconnect_deadline is None
        self.__reconnect_deadline = self._scheduler.add(self.__reconnect_period, self.on_reconnect_timeout)

    def on_connect_fail(self, reactor):
        """

        Parameters
        ----------
        reactor: Reactor
        """
        assert self.__reconnect_deadline is None
        self.__reconnect_deadline = self._scheduler.add(self.__reconnect_period, self.on_reconnect_timeout)

    def on_reconnect_timeout(self):
        """

        Parameters
        ----------
        reactor: Reactor
        """
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

    def on_connack(self, reactor, p):
        """

        Parameters
        ----------
        reactor: Reactor
        p: MqttConnack
        """
        sub_ticket = self.subscribe(self.__topics)
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
        super(type(self), self).start()


def create_parser():
    """
    Returns
    -------
    ArgumentParser
    """
    parser = ArgumentParser()
    parser.add_argument("hostname")
    parser.add_argument("port", type=int)
    parser.add_argument("--ssl", type=bool, help="Enable SSL/TLS encryption.")
    parser.add_argument("--clientid", help="Unique client id to use to connect to server.")
    parser.add_argument("--keepalive", type=int, default=5*60*1000, help="Ensures bytes are sent to server at least")
    parser.add_argument("-v", "--verbosity", action="count", default=0, help="increase output verbosity")
    parser.add_argument("--topic0", "--t0", action="append", default=[], help="Subscribe to topic with max QoS=0.")
    parser.add_argument("--topic1", "--t1", action="append", default=[], help="Subscribe to topic with max QoS=1.")
    parser.add_argument("--topic2", "--t2", action="append", default=[], help="Subscribe to topic with max QoS=2.")
    parser.add_argument("--keepalive", type=int, default=0,
                        help="Launches keepalive pings after this many seconds without sending data.")
    return parser


def main(args=sys.argv[1:]):
    parser = create_parser()
    ns = parser.parse_args(args)

    if ns.verbosity == 0:
        logging.basicConfig(format='%(asctime)-15s %(message)s',
                            level=logging.INFO,
                            stream=sys.stdout)
    elif ns.verbosity == 1:
        logging.basicConfig(format='%(asctime)-15s %(message)s',
                            level=logging.DEBUG,
                            stream=sys.stdout)
    else:
        raise NotImplementedError(ns.verbosity)

    #
    # 1883 : MQTT, unencrypted
    # 8883 : MQTT, encrypted
    # 8884 : MQTT, encrypted, client certificate required
    # 8080 : MQTT over WebSockets, unencrypted
    # 8081 : MQTT over WebSockets, encrypted
    #
    # from https://test.mosquitto.org/ (2018-09-19)
    #

    topics = []
    topics.extend(MqttTopic(topic, 0) for topic in ns.topic0)
    topics.extend(MqttTopic(topic, 1) for topic in ns.topic1)
    topics.extend(MqttTopic(topic, 2) for topic in ns.topic2)

    if not topics:
        topics = [MqttTopic('#', 0)]

    endpoint = (ns.hostname, ns.port)
    client = MqttSubClient(endpoint, topics,
                           clientid=ns.clientid,
                           keepalive_period=ns.keepalive,
                           ssl=ns.ssl)
    client.start()

    while client.state in ACTIVE_STATES:
        client.poll(5.)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))