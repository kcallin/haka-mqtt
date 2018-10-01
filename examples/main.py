import argparse
import logging
import ssl
import sys
import socket
from select import select
from ssl import wrap_socket
from time import time

from mqtt_codec import MqttTopic
from haka_mqtt.reactor import ReactorProperties, Reactor, ReactorState, INACTIVE_STATES
from haka_mqtt.clock import SystemClock
from haka_mqtt.scheduler import Scheduler

TOPIC = 'bubbles'
count = 0


def on_disconnect(reactor):
    pass


def on_connack(reactor, p):
    """

    Parameters
    ----------
    reactor: Reactor
    p: MqttConnack
    """
    reactor.subscribe([
        MqttTopic(TOPIC, 1),
    ])


def on_suback(reactor, p):
    """

    Parameters
    ----------
    reactor: Reactor
    p: MqttSuback
    """
    global count

    count += 1
    reactor.publish(TOPIC, str(count), 1)


def on_puback(reactor, p):
    """

    Parameters
    ----------
    reactor: Reactor
    p: MqttPuback
    """
    global count
    global limit


    if count == 50:
        reactor.terminate()
        reactor.start()
        count += 1
    elif count < 100:
        count += 1
        reactor.publish(TOPIC, str(count), 1)
    else:
        reactor.stop()


def on_publish(reactor, p):
    """

    Parameters
    ----------
    reactor: Reactor
    p: MqttPuback
    """
    pass


def create_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(0)

    return sock


def ssl_create_socket():
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(0)

    return ctx.wrap_socket(sock)


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
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)


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
    p = ReactorProperties()
    p.socket_factory = ssl_create_socket
    p.endpoint = endpoint
    p.clock = clock
    p.keepalive_period = 20
    p.client_id = 'bobby'
    p.scheduler = scheduler

    reactor = Reactor(p)
    reactor.on_suback = on_suback
    reactor.on_puback = on_puback
    reactor.on_connack = on_connack
    reactor.on_publish = on_publish
    reactor.start()

    log = logging.getLogger()

    last_poll_time = time()
    select_timeout = scheduler.remaining()
    while reactor.state not in (ReactorState.stopped, ReactorState.error):
        #
        #                                 |---------poll_period-------------|------|
        #                                 |--poll--|-----select_period------|
        #                                 |  dur   |
        #  ... ----|--------|-------------|--------|---------|--------------|------|---- ...
        #            select   handle i/o     poll     select    handle i/o    poll
        #
        if reactor.want_read():
            rlist = [reactor.socket]
        else:
            rlist = []

        if reactor.want_write():
            wlist = [reactor.socket]
        else:
            wlist = []

        rlist, wlist, xlist = select(rlist, wlist, [], select_timeout)

        for r in rlist:
            assert r == reactor.socket
            reactor.read()

        for w in wlist:
            assert w == reactor.socket
            reactor.write()

        poll_time = time()
        time_since_last_poll = poll_time - last_poll_time
        if scheduler.remaining() is not None:
            deadline_miss_duration = time_since_last_poll - scheduler.remaining()
            if deadline_miss_duration > 0:
                log.debug("Missed poll deadline by %fs.", deadline_miss_duration)

        if reactor.state in INACTIVE_STATES:
            reactor.start()

        scheduler.poll(time_since_last_poll)
        last_poll_time = poll_time

        select_timeout = scheduler.remaining()
        if select_timeout is not None:
            last_poll_duration = time() - last_poll_time
            select_timeout -= last_poll_duration

        if select_timeout < 0:
            select_timeout = 0

    #print(repr(reactor.error))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))