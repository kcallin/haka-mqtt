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
from haka_mqtt.frontends.event_queue import MqttEventEnqueue
from haka_mqtt.frontends.poll import MqttPollClientProperties, MqttPollClient


class UnexpectedMqttEventError(Exception):
    def __init__(self, e):
        """Raised when an unexpected MQTT event occurs.

        Parameters
        ----------
        e: mqtt_codec.packet.MqttPacketBody or haka_mqtt.frontends.event_queue.MqttConnectionEvent
        """
        self.event = e

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, repr(self.event))


class ExampleMqttClient(MqttEventEnqueue, MqttPollClient):
    """A helper class for polling mqtt events.

    It is critical that the order of inheritance is correct for this
    class to work correctly.  The :class:`MqttEventEnqueue` class *must* appear
    before :class:`MqttPollClient` so that its methods are called first.

    """
    def __init__(self, endpoint):
        properties = MqttPollClientProperties()
        properties.keepalive_period = 100
        properties.ssl = False
        properties.host, properties.port = endpoint
        properties.address_family = socket.AF_UNSPEC

        self.__q = Queue()
        MqttPollClient.__init__(self, properties)
        MqttEventEnqueue.__init__(self, self.__q)

    def poll_until_event(self, timeout=None):
        """Polls connection until an event occurs then returns it.  If
        timeout passes without an event occurring returns None.

        Parameters
        ----------
        timeout: float or None
            Maximum amount of time to wait for an event.  If None then
            waits forever.  Must satisfy condition ``timeout >= 0``.

        Returns
        -------
        mqtt_codec.packet.MqttPacketBody or MqttConnectionEvent or None
            None is returned if no event occurs.
        """
        if timeout is None:
            poll_end_time = None
        elif timeout >= 0:
            poll_end_time = self._clock.time() + timeout
        else:
            assert timeout < 0
            raise ValueError(timeout)

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

    def expect_event(self, predicate, timeout=None):
        """Waits any event to occur and returns it if
        ``predicate(event)`` returns ``True``; otherwise raises an
        exception.  If `timeout` expires before any event is received
        then returns `None`.

        Parameters
        ----------
        predicate: callable
            A callable that will be passed a single argument that will
            be of type :class:`mqtt_codec.packet.MqttPacketBody` or
            :class:`haka_mqtt.frontends.event_queue.MqttConnectionEvent`.
        timeout: float or None
            Maximum amount of time to wait for an event.  If None then
            waits forever.

        Raises
        ------
        UnexpectedMqttEventError
            The first even that occurs ``predicate(event)`` returns False.

        Returns
        -------
        mqtt_codec.packet.MqttPacketBody or haka_mqtt.frontends.event_queue.MqttConnectionEvent or None
            Returns an event matching predicate(e) or None if no such
            event occurred before timeout.
        """
        while True:
            e = self.poll_until_event(timeout=timeout)
            if e is None or predicate(e):
                return e
            else:
                raise UnexpectedMqttEventError(e)


def argparse_endpoint(s):
    """Splits an incoming string into host and port components.

    >>> argparse_endpoint('localhost:1883')
    ('localhost', 1883)

    Parameters
    ----------
    s: str

    Raises
    -------
    ArgumentTypeError
        Raised when port number is out of range 1 <= port <= 65535, when
        port is not an integer, or when there is more than one colon in
        the string.

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
    """Creates a command-line argument parser used by the program main
    method.

    Returns
    -------
    ArgumentParser
    """
    parser = ArgumentParser()
    parser.add_argument("endpoint", type=argparse_endpoint)

    return parser


def run(client):
    """
    Raises
    -------
    UnexpectedMqttEventError

    Parameters
    ----------
    client: ExampleMqttClient
    """
    client.start()

    topic = client.client_id
    client.expect_event(lambda e: e == MqttConnack(False, ConnackResult.accepted))
    subscribe = client.subscribe([MqttTopic(topic, 1)])
    client.expect_event(lambda e: e == MqttSuback(subscribe.packet_id, [SubscribeResult.qos1]))

    UTF8 = 'utf-8'

    seq_num = 0
    while True:
        payload = str(seq_num).encode(UTF8)
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
            raise UnexpectedMqttEventError(e)
        seq_num += 1

        client.poll(1)


def main(args=sys.argv[1:]):
    """Parses arguments and passes them to :func:`run` method.  Returns
    one when an error occurs.

    Returns
    --------
    int
    """
    logging.basicConfig(format='%(asctime)-15s %(name)s %(levelname)s %(message)s', level=logging.DEBUG, stream=sys.stdout)

    parser = create_parser()
    ns = parser.parse_args(args)

    try:
        run(ExampleMqttClient(ns.endpoint))
    except Exception as e:
        logging.critical('Panicked because of exception.', exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))