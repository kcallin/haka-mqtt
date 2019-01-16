"""An MQTT client that demonstrates a select-based polling interface.

A loopback client that subscribes to a topic that it publishes to.
Every time a message is published it should be echoed back to the
client by the remote MQTT broker.
"""

from __future__ import print_function
import logging
import socket
import sys
from Queue import Empty, Queue
from argparse import ArgumentParser, ArgumentTypeError

# 3rd Party Imports
from mqtt_codec.packet import (
    MqttTopic,
    MqttConnack,
    ConnackResult,
    MqttSuback,
    SubscribeResult,
    MqttPublish,
    MqttPuback,
)
from haka_mqtt.frontends.event_queue import MqttEventQueue
from haka_mqtt.frontends.poll import MqttPollClientProperties, MqttPollClient

# Your Imports (if any)


# Your software.


class ExampleMqttClient(MqttEventQueue, MqttPollClient):
    def __init__(self, endpoint):
        properties = MqttPollClientProperties()
        properties.keepalive_period = 100
        properties.ssl = False
        properties.host, properties.port = endpoint
        properties.address_family = socket.AF_UNSPEC

        self.__q = Queue()
        MqttPollClient.__init__(self, properties)
        MqttEventQueue.__init__(self, self.__q)

    def poll_until_event(self, timeout=None):
        """

        Parameters
        ----------
        timeout: float or None
            Maximum amount of time to wait for an event.  If None then
            waits forever.

        Returns
        -------
        MqttPacketBody or MqttConnectionEvent or None
            None is returned if no event occurs.
        """
        if timeout is None:
            poll_end_time = None
        else:
            poll_end_time = self._clock.time() + timeout

        e = None
        while poll_end_time is None or self._clock.time() < poll_end_time:
            try:
                reactor, event = self.__q.get_nowait()
                e = event
                break
            except Empty:
                pass

            select_timeout = self._scheduler.remaining()
            if poll_end_time is not None:
                if select_timeout is None or self._clock.time() + select_timeout > poll_end_time:
                    select_timeout = poll_end_time - self._clock.time()

                if select_timeout < 0.:
                    select_timeout = 0

            self._selector.select(select_timeout)
            self._scheduler.poll()

        return e

    def expect_event(self, matcher, timeout=None):
        """Waits for an event and returns it if ``matcher(event)``
        returns ``True``; otherwise raises an exception.  If `timeout`
        expires before any event is received then returns `None`.

        Parameters
        ----------
        timeout: float or None
            Maximum amount of time to wait for an event.  If None then
            waits forever.

        Raises
        ------
        NotImplementedError
            When an event occurs for which matcher(event) returns False.

        Returns
        -------
        mqtt_codec.packet.MqttPacketBody or MqttConnectionEvent or None
            Returns an event matching matcher(e) or None if no such
            event occurred before timeout.
        """
        while True:
            e = self.poll_until_event(timeout=timeout)
            if e is None:
                return None
            elif matcher(e):
                return e
            else:
                raise NotImplementedError(e)


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
        raise ArgumentTypeError('Format of endpoint must be hostname:port.')
    host, port = words

    try:
        port = int(port)
        if not 1 <= port <= 2**16-1:
            raise ArgumentTypeError('Port must be in the range 1 <= port <= 65535.')
    except ValueError:
        raise ArgumentTypeError('Format of endpoint must be hostname:port.')

    return host, port


def create_parser():
    """

    Returns
    -------
    ArgumentParser
    """
    parser = ArgumentParser()
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

    topic = client.client_id
    client.expect_event(lambda e: e == MqttConnack(False, ConnackResult.accepted))
    subscribe = client.subscribe([MqttTopic(topic, 1)])
    client.expect_event(lambda e: e == MqttSuback(subscribe.packet_id, [SubscribeResult.qos1]))

    seq_num = 0
    while True:
        payload = str(seq_num).encode('utf-8')
        publish = client.publish(topic, payload, 1)
        e = client.poll_until_event()

        # It isn't clear whether the publish or puback should return
        # first; need to be prepared for either case.
        #
        if isinstance(e, MqttPublish) and e.payload == payload:
            client.expect_event(lambda e: e == MqttPuback(publish.packet_id))
        elif e == MqttPuback(publish.packet_id):
            client.expect_event(lambda e: isinstance(e, MqttPublish) and e.payload == payload)
        else:
            raise NotImplemented(e)
        seq_num += 1

        client.poll(1)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))