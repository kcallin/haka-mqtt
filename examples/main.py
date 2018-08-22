import logging
import sys
import socket
from select import select
from time import time

from haka_mqtt.mqtt import MqttTopic
from haka_mqtt.reactor import ReactorProperties, SystemClock, Reactor, ReactorState
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

    if count < 10:
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


def main():
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(0)
    endpoint = ('test.mosquitto.org', 1883)
    clock = SystemClock()

    scheduler = Scheduler()
    p = ReactorProperties()
    p.socket = sock
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

        scheduler.poll(time_since_last_poll)
        last_poll_time = poll_time

        select_timeout = scheduler.remaining()
        if select_timeout is not None:
            last_poll_duration = time() - last_poll_time
            select_timeout -= last_poll_duration

    print(repr(reactor.error))


if __name__ == '__main__':
    sys.exit(main())