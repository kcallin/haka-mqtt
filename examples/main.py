import argparse
import logging
import ssl
import sys
import socket
from select import select
from time import time

from haka_mqtt.dns import SynchronousDnsResolver, AsyncDnsResolver
from mqtt_codec.packet import MqttTopic, MqttControlPacketType
from haka_mqtt.reactor import ReactorProperties, Reactor, ReactorState, INACTIVE_STATES
from haka_mqtt.clock import SystemClock
from haka_mqtt.scheduler import Scheduler

TOPIC = 'bubbles'
count = 0


class MqttClient():
    def __init__(self, properties):
        """

        Parameters
        ----------
        properties: ReactorProperties
        """
        self.__scheduler = properties.scheduler
        reactor = Reactor(properties)
        reactor.on_suback = self.__on_suback
        reactor.on_puback = self.__on_puback
        reactor.on_connack = self.__on_connack
        reactor.on_publish = self.__on_publish
        reactor.on_disconnect = self.__on_disconnect
        reactor.on_connect_fail = self.__on_connect_fail
        self.__reactor = reactor
        self.__publish_queue = []
        self.__puback_queue = []
        self.__running = False

        self.__pub_deadline = None

    def is_running(self):
        return self.__running

    def __on_disconnect(self, reactor):
        print('disconnect', repr(reactor.error))

    def __on_connect_fail(self, reactor):
        print('connect_fail', repr(reactor.error))

    def __on_suback(self, reactor, p):
        """

        Parameters
        ----------
        reactor: Reactor
        p: MqttSuback
        """

        publish = self.__reactor.publish(TOPIC, str(count), 1)
        self.__publish_queue.append(publish)

    def __on_puback(self, reactor, p):
        """

        Parameters
        ----------
        reactor: Reactor
        p: mqtt_codec.packet.MqttPuback
        """

        assert p.packet_type is MqttControlPacketType.puback
        assert p.packet_id == self.__publish_queue[-1].packet_id

        if len(self.__publish_queue) % 2 == 0:
            publish = self.__reactor.publish(TOPIC, str(len(self.__publish_queue)), 1)
            self.__publish_queue.append(publish)
        else:
            self.__pub_deadline = self.__scheduler.add(30., self.__on_pub_timeout)

    def __on_pub_timeout(self):
        publish = self.__reactor.publish(TOPIC, str(len(self.__publish_queue)), 1)
        self.__publish_queue.append(publish)
        self.__pub_deadline.cancel()
        self.__pub_deadline = None

    def __on_connack(self, reactor, p):
        """

        Parameters
        ----------
        reactor: Reactor
        p: MqttConnack
        """
        self.__reactor.subscribe([
            MqttTopic(TOPIC, 1),
        ])

    def __on_publish(self, reactor, p):
        """

        Parameters
        ----------
        reactor: Reactor
        p: MqttPuback
        """
        pass

    @property
    def socket(self):
        return self.__reactor.socket

    def want_read(self):
        return self.__reactor.want_read()

    def read(self):
        return self.__reactor.read()

    def want_write(self):
        return self.__reactor.want_write()

    def write(self):
        return self.__reactor.write()

    def start(self):
        self.__reactor.start()
        self.__running = True


def create_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(0)

    return sock


def ssl_create_socket():
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock = ctx.wrap_socket(sock)
    sock.setblocking(0)

    return sock


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

    parser = create_parser()
    ns = parser.parse_args(args)

    endpoint = ns.endpoint
    clock = SystemClock()

    scheduler = Scheduler()

    async_name_resolver = AsyncDnsResolver()

    p = ReactorProperties()
    p.socket_factory = ssl_create_socket
    p.endpoint = endpoint
    p.clock = clock
    p.keepalive_period = 10
    p.client_id = 'bobby'
    p.scheduler = scheduler
    p.name_resolver = SynchronousDnsResolver()
    p.name_resolver = async_name_resolver

    client = MqttClient(p)
    client.start()

    log = logging.getLogger()

    last_poll_time = time()
    select_timeout = scheduler.remaining()
    while client.is_running():
        #
        #                                 |---------poll_period-------------|------|
        #                                 |--poll--|-----select_period------|
        #                                 |  dur   |
        #  ... ----|--------|-------------|--------|---------|--------------|------|---- ...
        #            select   handle i/o     poll     select    handle i/o    poll
        #
        rlist = [async_name_resolver.read_fd()]
        if client.want_read():
            rlist.append(client.socket)

        if client.want_write():
            wlist = [client.socket]
        else:
            wlist = []

        if select_timeout is None:
            pass
            #log.debug('Enter select None')
        else:
            pass
            #log.debug('Enter select %f', select_timeout)
        rlist, wlist, xlist = select(rlist, wlist, [], select_timeout)
        #log.debug('Exit select')

        for r in rlist:
            if r == client.socket:
                client.read()
            elif r == async_name_resolver.read_fd():
                async_name_resolver.poll()
            else:
                raise NotImplementedError()

        for w in wlist:
            assert w == client.socket
            #log.debug('Calling write')
            client.write()

        poll_time = time()
        time_since_last_poll = poll_time - last_poll_time
        if scheduler.remaining() is not None:
            deadline_miss_duration = time_since_last_poll - scheduler.remaining()
            if deadline_miss_duration > 0:
                log.debug("Missed poll deadline by %fs.", deadline_miss_duration)

        scheduler.poll(time_since_last_poll)
        last_poll_time = poll_time

        select_timeout = scheduler.remaining()
        if select_timeout is not None:
            last_poll_duration = time() - last_poll_time
            select_timeout -= last_poll_duration

        assert None < 0

        if select_timeout is not None and select_timeout < 0:
            select_timeout = 0

    #print(repr(reactor.error))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))