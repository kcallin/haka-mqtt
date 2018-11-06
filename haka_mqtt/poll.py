import os
import socket
import ssl
from datetime import datetime
from select import select
from time import sleep

from haka_mqtt.clock import SystemClock
from haka_mqtt.dns_async import AsyncFutureDnsResolver
from haka_mqtt.dns_sync import SynchronousFutureDnsResolver
from haka_mqtt.reactor import ReactorProperties, Reactor, ACTIVE_STATES
from haka_mqtt.scheduler import ClockScheduler
from haka_mqtt.socket_factory import SslSocketFactory, SocketFactory, BlockingSocketFactory, BlockingSslSocketFactory


def generate_client_id():
    """Generates a client id based on current time, hostname, and
    process-id.

    Returns
    -------
    str
    """
    return 'client-{}-{}-{}'.format(
        datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        socket.gethostname(),
        os.getpid())


class _PollClientSelector(object):
    def __init__(self, async_dns_resolver):
        self.__rmap = {async_dns_resolver.read_fd(): async_dns_resolver.poll}
        self.__wmap = {}

    def add_read(self, fd, reactor):
        """
        Parameters
        ----------
        fd: file descriptor
            File-like object.
        reactor: haka_mqtt.reactor.Reactor
        """
        self.__rmap[fd] = reactor.read

    def del_read(self, fd, reactor):
        """
        Parameters
        ----------
        fd: file descriptor
            File-like object.
        reactor: haka_mqtt.reactor.Reactor
        """
        del self.__rmap[fd]

    def add_write(self, fd, reactor):
        """
        Parameters
        ----------
        fd: file descriptor
            File-like object.
        reactor: haka_mqtt.reactor.Reactor
        """
        self.__wmap[fd] = reactor.write

    def del_write(self, fd, reactor):
        """
        Parameters
        ----------
        fd: file descriptor
            File-like object.
        reactor: haka_mqtt.reactor.Reactor
        """
        del self.__wmap[fd]

    def select(self, select_timeout=None):
        rlist, wlist, xlist = select(self.__rmap.keys(), self.__wmap.keys(), [], select_timeout)
        for fd in rlist:
            self.__rmap[fd]()

        for fd in wlist:
            self.__wmap[fd]()


class MqttPollClientProperties(object):
    """
    Attributes
    ----------
    client_id: str optional
        The MQTT client id to pass to the MQTT server.  A client id will
        be randomly generated based on .
    address_family: int
        Address family; one of the socket.AF_* constants (eg.
        socket.AF_UNSPEC for any family, socket.AF_INET for IP4
        socket.AF_INET6 for IP6).
    """
    def __init__(self):
        self.host = None
        self.port = None
        self.client_id = None
        self.keepalive_period = 0
        self.ssl = True
        self.address_family = socket.AF_UNSPEC


class MqttPollClient(Reactor):
    """

    Parameters
    ----------
    properties: MqttPollClientProperties
    """
    def __init__(self, properties, log='haka'):
        self._clock = SystemClock()
        self._scheduler = ClockScheduler(self._clock)
        self._async_name_resolver = AsyncFutureDnsResolver()
        self._selector = _PollClientSelector(self._async_name_resolver)

        endpoint = (properties.host, properties.port)

        p = ReactorProperties()
        if properties.ssl:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            p.socket_factory = SslSocketFactory(ssl_context)
        else:
            p.socket_factory = SocketFactory()

        p.endpoint = endpoint
        p.keepalive_period = properties.keepalive_period
        if properties.client_id is None:
            p.client_id = generate_client_id()
        else:
            p.client_id = properties.client_id
        p.scheduler = self._scheduler
        p.name_resolver = self._async_name_resolver
        p.selector = self._selector
        p.address_family = properties.address_family

        Reactor.__init__(self, p, log=log)

    def poll(self, period=0.):
        poll_end_time = self._clock.time() + period

        while self._clock.time() < poll_end_time and self.state in ACTIVE_STATES:
            select_timeout = self._scheduler.remaining()
            if select_timeout is None or self._clock.time() + select_timeout > poll_end_time:
                select_timeout = poll_end_time - self._clock.time()

            if select_timeout < 0.:
                select_timeout = 0

            self._selector.select(select_timeout)
            self._scheduler.poll()


class BlockingMqttClient(Reactor):
    """

    Parameters
    ----------
    properties: MqttPollClientProperties
    """
    def __init__(self, properties, log='haka'):
        self._clock = SystemClock()
        self._scheduler = ClockScheduler(self._clock)

        endpoint = (properties.host, properties.port)

        p = ReactorProperties()
        if properties.ssl:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            p.socket_factory = BlockingSslSocketFactory(ssl_context)
        else:
            p.socket_factory = BlockingSocketFactory()

        p.endpoint = endpoint
        p.keepalive_period = properties.keepalive_period
        if properties.client_id is None:
            p.client_id = generate_client_id()
        else:
            p.client_id = properties.client_id
        p.scheduler = self._scheduler
        p.name_resolver = SynchronousFutureDnsResolver()
        p.address_family = properties.address_family

        Reactor.__init__(self, p, log=log)

    def poll(self, period=0.):
        poll_end_time = self._clock.time() + period

        while self._clock.time() < poll_end_time and self.state in ACTIVE_STATES:
            select_timeout = self._scheduler.remaining()
            if select_timeout is None or self._clock.time() + select_timeout > poll_end_time:
                select_timeout = poll_end_time - self._clock.time()

            if select_timeout <= 0.:
                select_timeout = 0.00001

            if self.socket is not None:
                self.socket.settimeout(select_timeout)

            if self.want_write():
                self.write()
            elif self.want_read():
                self.read()
            else:
                sleep(select_timeout)

            self._scheduler.poll()
