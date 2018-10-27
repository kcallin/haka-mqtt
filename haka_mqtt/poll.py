import socket
import ssl
from select import select

from haka_mqtt.clock import SystemClock
from haka_mqtt.dns_async import AsyncFutureDnsResolver
from haka_mqtt.reactor import ReactorProperties, Reactor
from haka_mqtt.scheduler import Scheduler, ClockScheduler
from haka_mqtt.socket_factory import SslSocketFactory, SocketFactory


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
        p.client_id = properties.client_id
        p.scheduler = self._scheduler
        p.name_resolver = self._async_name_resolver
        p.selector = self._selector
        p.address_family = properties.address_family

        Reactor.__init__(self, p, log=log)

    def poll(self, period=0.):
        poll_end_time = self._clock.time() + period

        while self._clock.time() < poll_end_time:
            select_timeout = self._scheduler.remaining()
            if select_timeout is None or self._clock.time() + select_timeout > poll_end_time:
                select_timeout = poll_end_time - self._clock.time()

            if select_timeout < 0.:
                select_timeout = 0

            self._selector.select(select_timeout)
            self._scheduler.poll()
