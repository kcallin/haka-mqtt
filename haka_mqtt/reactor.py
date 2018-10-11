import errno
import socket
import logging
import ssl
from binascii import b2a_hex
from io import BytesIO
import os

from enum import (
    IntEnum,
    unique,
)

from haka_mqtt.clock import SystemClock
from haka_mqtt.cycle_iter import IntegralCycleIter
from mqtt_codec.io import (
    UnderflowDecodeError,
    DecodeError,
    BytesReader,
)
from mqtt_codec.packet import (
    MqttControlPacketType,
    MqttFixedHeader,
    MqttConnect,
    ConnackResult,
    MqttConnack,
    MqttSubscribe,
    SubscribeResult,
    MqttSuback,
    MqttPublish,
    MqttPuback,
    MqttPubrec,
    MqttPubrel,
    MqttPubcomp,
    MqttPingreq,
    MqttPingresp,
    MqttDisconnect
)
from haka_mqtt.mqtt_request import (
    MqttSubscribeTicket,
    MqttUnsubscribeRequest,
    MqttPublishTicket,
    MqttPublishStatus,
    MqttSubscribeStatus,
)
from haka_mqtt.on_str import HexOnStr, ReprOnStr


class ReactorProperties(object):
    """
    Attributes
    ----------
    socket_factory: haka_mqtt.socket_factory.SocketFactory
    client_id: str
    clock:
    endpoint: tuple
        2-tuple of (host: `str`, port: `int`).  The `port` value is
        constrainted such that 0 <= `port` <= 2**16-1.
    keepalive_period: int
        0 <= keepalive_period <= 2*16-1
    clean_session: bool
        With clean session set to True reactor will clear all message
        buffers on disconnect without regard to QoS; otherwise
        unacknowledged messages will be retransmitted after a
        re-connect.
    name_resolver: callable
        DNS resolver.
    username: str optional
    password: str optional
    """
    def __init__(self):
        self.socket_factory = None
        self.endpoint = None
        self.client_id = None
        self.clock = SystemClock()
        self.keepalive_period = 10*60
        self.scheduler = None
        self.clean_session = True
        self.name_resolver = None
        self.username = None
        self.password = None


@unique
class ReactorState(IntEnum):
    """
    Inactive states are those where there are no active deadlines, the
    socket is closed and there is no active I/O.  Active states are
    those where any of these characteristics is not met.

    Active States:

    * :py:const:`ReactorState.init`
    * :py:const:`ReactorState.stopped`
    * :py:const:`ReactorState.error`

    Inactive States:

    * :py:const:`ReactorState.connecting`
    * :py:const:`ReactorState.handshake`
    * :py:const:`ReactorState.connack`
    * :py:const:`ReactorState.connected`
    * :py:const:`ReactorState.stopping`

    """
    init = 0
    name_resolution = 1
    connecting = 2
    handshake = 3
    connack = 4
    connected = 5
    stopping = 6
    mute = 7
    stopped = 8
    error = 9


# States where there are no active deadlines, the socket is closed and there
# is no active I/O.
#
INACTIVE_STATES = (ReactorState.init, ReactorState.stopped, ReactorState.error)

# States with active deadlines, open sockets, or pending I/O.
#
ACTIVE_STATES = (
    ReactorState.name_resolution,
    ReactorState.connecting,
    ReactorState.handshake,
    ReactorState.connack,
    ReactorState.connected,
    ReactorState.stopping,
    ReactorState.mute,
)


assert set(INACTIVE_STATES).union(ACTIVE_STATES) == set(iter(ReactorState))


def index(l, predicate):
    """

    Parameters
    ----------
    l: list
    predicate: callable
        Callable function taking a single parameter.

    Returns
    -------
    int or None
        Index of first matching predicate or None if no such element found.
    """
    assert callable(predicate), repr(predicate)

    for idx, e in enumerate(l):
        if predicate(e):
            rv = idx
            break
    else:
        rv = None

    return rv


class ReactorFail(object):
    pass


class MutePeerReactorFail(ReactorFail):
    """Error that occurs when the server closes its write stream
    unexpectedly."""
    pass


class ConnectReactorFail(ReactorFail):
    """Error that occurs when the server sends a connack fail in
    response to an initial connect packet."""
    def __init__(self, result):
        assert result != ConnackResult.accepted
        self.__result = result

    @property
    def result(self):
        """ConnackResult: guaranteed that value is not `ConnackResult.accepted`."""
        return self.__result

    def __eq__(self, other):
        return hasattr(other, 'result') and self.result == other.result


class KeepaliveTimeoutReactorFail(ReactorFail):
    """Server fails to respond in a timely fashion."""
    def __eq__(self, other):
        return isinstance(other, KeepaliveTimeoutReactorFail)

    def __repr__(self):
        return '{}()'.format(self.__class__.__name__)


class SocketReactorFail(ReactorFail):
    """A socket call failed.

    Parameters
    ----------
    errno_val: int
    """
    def __init__(self, errno_val):
        assert errno_val in errno.errorcode, errno_val

        self.__errno = errno_val

    @property
    def errno(self):
        """int: value in `errno.errorcode`."""
        return self.__errno

    def __repr__(self):
        return 'SocketError(<{}: {}>)'.format(errno.errorcode[self.errno], self.errno)

    def __eq__(self, other):
        return self.errno == other.errno


class AddressReactorFail(ReactorFail):
    """Failed to lookup a valid address.

    Parameters
    ----------
    gaierror: socket.gaierror
    """

    def __init__(self, gaierror):
        assert isinstance(gaierror, socket.gaierror)
        self.__gaierror = gaierror

    @property
    def gaierror(self):
        """socket.gaierror: Addressing error."""
        return self.__gaierror

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, repr(self.gaierror))

    def __eq__(self,  other):
        return (
            hasattr(other, 'gaierror')
            and self.gaierror.errno == other.gaierror.errno
            and hasattr(other, 'gaierror')
            and self.gaierror.message == other.gaierror.message
        )


class DecodeReactorFail(ReactorFail):
    """Server wrote a sequence of bytes that could not be interpreted as
    an MQTT packet."""
    def __init__(self, description):
        self.description = description


class ProtocolReactorFail(ReactorFail):
    """Server send an inappropriate MQTT packet to the client."""
    def __init__(self, description):
        self.description = description


class Reactor:
    """
    Parameters
    ----------
    properties: ReactorProperties

    standard_preflight_queue
    prompt_preflight_queue
    flight_queue

       ---pub(1) ---->
       <--pubrec(1)---

    send_queue
    """
    def __init__(self, properties):
        assert properties.client_id is not None
        assert properties.socket_factory is not None
        assert properties.endpoint is not None
        assert properties.scheduler is not None
        assert 0 <= properties.keepalive_period <= 2**16-1
        assert isinstance(properties.keepalive_period, int)
        assert isinstance(properties.clean_session, bool)
        assert callable(properties.name_resolver)
        host, port = properties.endpoint
        assert isinstance(host, str)
        assert 0 <= port <= 2**16-1
        assert isinstance(port, int)

        self.__log = logging.getLogger('haka')
        self.__wbuf = bytearray()  #
        self.__rbuf = bytearray()  #

        self.__ssl_want_read = False  #
        self.__ssl_want_write = False  #

        self.__client_id = properties.client_id
        self.__username = properties.username
        self.__password = properties.password

        self.__clock = properties.clock
        self.__keepalive_period = properties.keepalive_period
        self.__keepalive_due_deadline = None
        self.__keepalive_abort_deadline = None
        self.__clean_session = properties.clean_session
        self.__name_resolver = properties.name_resolver

        self.__socket_factory = properties.socket_factory
        self.socket = None
        self.__host, self.__port = properties.endpoint
        self.__enable = False
        self.__state = ReactorState.init
        self.__error = None

        self.__send_packet_ids = set()
        self.__send_path_packet_id_iter = IntegralCycleIter(0, 2 ** 16)

        self.__preflight_queue = []
        self.__inflight_queue = []

        # Publish packets must be ack'd in order of publishing
        # [MQTT-4.6.0-2], [MQTT-4.6.0-3]
        #self.__in_flight_publish = []

        # No specific requirement exists for subscribe suback ordering.
        # self.__in_flight_subscribe = {}

        # It MUST send PUBREL packets in the order in which the corresponding PUBREC packets were
        # received (QoS 2 messages) [MQTT-4.6.0-4]
        #self.__in_flight_pubrel = []

        self.__ping_active = False
        self.__scheduler = properties.scheduler

        # Want read
        self.__want_read = False
        self.__want_write = False

        self.on_want_read = None
        self.on_want_write = None

        # Connection Callbacks
        self.on_connect_fail = None
        self.on_disconnect = None
        self.on_connack = None

        # Send path
        self.on_pubrec = None
        self.on_pubcomp = None

        # Subscribe path
        self.on_suback = None

        # Receive path
        self.on_publish = None
        # TODO: Find place for this documentation.
        # on_puback(puback); at time of call the associated MqttPublishTicket will have status set to done.
        self.on_puback = None
        self.on_pubrel = None

    @property
    def clean_session(self):
        """bool: Clean session flag is true/false."""
        return self.__clean_session

    @property
    def client_id(self):
        """str: Client id."""
        return self.__client_id

    @property
    def keepalive_period(self):
        """float: If this period elapses without the client sending a
        control packet to the server then it will generate a pingreq
        packet and send it to the server."""
        return self.__keepalive_period

    @property
    def keepalive_timeout_period(self):
        """float: If the Keep Alive value is non-zero and the Server
        does not receive a Control Packet from the Client within one and
        a half times the Keep Alive time period, it MUST disconnect the
        Network Connection to the Client as if the network had failed.
        [MQTT-3.1.2-24]"""
        return int(self.keepalive_period * 1.5)

    @property
    def error(self):
        """ReactorError or None"""
        return self.__error

    @property
    def state(self):
        """ReactorState: Current reactor state."""
        return self.__state

    @property
    def enable(self):
        """bool: True when enabled; False disabled."""
        return self.__enable

    def __want_rw_update(self):
        if self.__want_write != self.want_write():
            self.__want_write = self.want_write()

            if self.on_want_write is not None:
                self.on_want_write(self)

        if self.__want_read != self.want_read():
            self.__want_read = self.want_read()

            if self.on_want_read is not None:
                self.on_want_read(self)

    def __assert_state_rules(self):
        if self.want_write() or self.want_read():
            assert self.socket is not None

        if self.state in INACTIVE_STATES:
            assert self.__keepalive_due_deadline is None
            assert self.__keepalive_abort_deadline is None

        if self.state in (ReactorState.name_resolution,
                          ReactorState.connecting):
            assert self.__keepalive_due_deadline is None
            assert self.__keepalive_abort_deadline is None

        if self.state is ReactorState.mute:
            assert self.__keepalive_due_deadline is None

        if self.state is ReactorState.error:
            assert self.error is not None

    def active_send_packet_ids(self):
        return set(self.__send_packet_ids)

    def in_flight_packets(self):
        return list(self.__inflight_queue)

    def preflight_packets(self):
        return list(self.__preflight_queue)

    def subscribe(self, topics):
        """

        Parameters
        ----------
        topics: iterable of MqttTopic

        Returns
        --------
        MqttSubscribeTicket
        """
        assert self.state == ReactorState.connected

        self.__assert_state_rules()

        req = MqttSubscribeTicket(self.__acquire_packet_id(), topics)
        self.__preflight_queue.append(req)

        self.__assert_state_rules()
        self.__want_rw_update()
        return req

    def __acquire_packet_id(self):
        packet_id = next(self.__send_path_packet_id_iter)
        self.__send_packet_ids.add(packet_id)
        return packet_id

    def unsubscribe(self, topics):
        """

        Parameters
        ----------
        topics: iterable of str

        Returns
        --------
        MqttUnsubscribeRequest
        """
        assert self.state == ReactorState.connected

        self.__assert_state_rules()

        req = MqttUnsubscribeRequest(self.__acquire_packet_id(), topics)
        self.__preflight_queue.append(req)

        self.__assert_state_rules()
        self.__want_rw_update()
        return req

    def publish(self, topic, payload, qos, retain=False):
        """Publish may be called in any state.  It will place a packet
        onto the preflight queue but no packet_id will be assigned
        until the packet is placed in-flight.

        Parameters
        -----------
        topic: str
        payload: bytes
        qos: int
            0 <= qos <= 2
        retain: bool

        Return
        -------
        MqttPublishTicket
        """
        self.__assert_state_rules()
        assert 0 <= qos <= 2

        req = MqttPublishTicket(self.__acquire_packet_id(), topic, payload, qos, retain)
        self.__preflight_queue.append(req)
        self.__assert_state_rules()
        self.__want_rw_update()
        return req

    def __start(self):
        assert self.state in INACTIVE_STATES
        assert self.enable is False

        self.__log.info('Starting.')

        self.__enable = True
        self.__error = None

        self.__ssl_want_write = False
        self.__ssl_want_read = False

        self.__ping_active = False

        preflight_queue = []
        for p in self.__inflight_queue:
            if p.packet_type is MqttControlPacketType.publish:
                # Publish packets in self.__inflight_queue will be
                # re-transmitted and the dupe flag must be set on the
                # re-transmitted packet.
                #
                # [MQTT-3.3.1.-1]
                #
                if p.qos == 1:
                    assert p.status is MqttPublishStatus.puback, p.status
                    p._set_dupe()
                elif p.qos == 2:
                    if p.status is MqttPublishStatus.pubrec:
                        p._set_dupe()
                else:
                    raise NotImplementedError(p.qos)
                preflight_queue.append(p)

        for p in self.__preflight_queue:
            if p.packet_type in (MqttControlPacketType.publish, MqttControlPacketType.pubrel):
                preflight_queue.append(p)

        self.socket = None
        self.__inflight_queue = []
        self.__preflight_queue = preflight_queue

        self.__wbuf = bytearray()
        self.__rbuf = bytearray()

        self.__state = ReactorState.name_resolution

        try:
            self.__log.info('Looking up host %s:%d.', self.__host, self.__port)
            results = self.__name_resolver(self.__host,
                                           self.__port,
                                           socktype=socket.SOCK_STREAM,
                                           proto=socket.IPPROTO_TCP,
                                           callback=self.__on_name_resolution)
        except socket.gaierror as e:
            self.__on_name_resolution(e)
        else:
            if results is not None:
                self.__on_name_resolution(results)

    def __on_name_resolution(self, results):
        """Called when hostname resolution is complete.

        Parameters
        ----------
        results: 5-tuple
            A 5-tuple of (family, socktype, proto, canonname, sockaddr).

        """
        assert results is not None

        # TODO: Termination of async dns query.
        if self.enable:
            if isinstance(results, socket.gaierror):
                e = results
                self.__log.error('%s (errno=%d).  Aborting.', e.strerror, e.errno)
                self.__abort(AddressReactorFail(e))
            else:
                if len(results) == 0:
                    self.__log.error('No hostname entries found.  Aborting.')
                    self.__abort(AddressReactorFail(socket.gaierror(socket.EAI_NONAME, 'Name or service not known')))
                elif len(results) > 0:
                    self.__log_name_resolution(results[0], chosen=True)
                    for result in results[1:]:
                        self.__log_name_resolution(result)
                    self.__connect(results[0])
                else:
                    raise NotImplementedError(len(results))
        else:
            self.__terminate(ReactorState.stopped, None)

    def __log_name_resolution(self, resolution, chosen=False):
        """Called when hostname resolution is complete.

        Parameters
        ----------
        resolution: 5-tuple
            A 5-tuple of (family, socktype, proto, canonname, sockaddr).
        chosen: bool
            True if this log entry is to be marked as a chosen sockaddr
            to connect to.
        """
        family, socktype, proto, canonname, sockaddr = resolution

        socktype_str = {
            socket.SOCK_DGRAM: 'sock_dgram',
            socket.SOCK_STREAM: 'sock_stream',
            socket.SOCK_RAW: 'sock_raw',
        }.get(socktype, str(socktype))

        proto_str = {
            socket.IPPROTO_TCP: 'tcp',
            socket.IPPROTO_IP: 'ip',
            socket.IPPROTO_UDP: 'udp',
        }.get(proto, str(proto))

        if chosen:
            chosen_postfix = ' (chosen)'
        else:
            chosen_postfix = ' '

        if family == socket.AF_INET:
            ip, port = sockaddr
            self.__log.info("Found family=inet sock=%s proto=%s addr=%s:%d%s", socktype_str, proto_str, ip, port, chosen_postfix)
        elif family == socket.AF_INET6:
            ip6, port, flow_info, scope_id = sockaddr
            self.__log.info("Found family=inet6 sock=%s proto=%s addr=%s:%d%s", socktype_str, proto_str, ip6, port, chosen_postfix)
        else:
            raise NotImplementedError()

    def __connect(self, resolution):
        """Connect to the given resolved address.

        Parameters
        ----------
        resolution: 5-tuple
            A 5-tuple of (family, socktype, proto, canonname, sockaddr)
            as returned by `socket.getaddrinfo`."""
        family, socktype, proto, canonname, sockaddr = resolution
        try:
            self.__state = ReactorState.connecting
            self.socket = self.__socket_factory()
            self.socket.connect(sockaddr)
        except socket.error as e:
            if e.errno == errno.EINPROGRESS:
                # Connection in progress.
                self.__log.info("Connecting.")
            else:
                self.__abort_socket_error(SocketReactorFail(e.errno))
        else:
            self.__on_connect()

    def start(self):
        """Attempts to connect with remote if in one of the inactive
        states :py:const:`ReactorState.init`,
        :py:const:`ReactorState.stopped`,
        :py:const:`ReactorState.error`.  The method has no effect if
        already in an active state.
        """
        self.__assert_state_rules()

        if self.state in INACTIVE_STATES:
            self.__start()
        elif self.state in (ReactorState.name_resolution, ReactorState.connecting, ReactorState.connack):
            self.__log.warning("Start while already connecting to server; taking no additional action.")
        elif self.state is ReactorState.connected:
            self.__log.warning("Start while already connected; taking no action.")
        elif self.state is (ReactorState.stopping, ReactorState.mute):
            self.__log.warning("Start while already stopping; stop process cannot be aborted.")
        else:
            raise NotImplementedError(self.state)

        self.__assert_state_rules()
        self.__want_rw_update()

    def stop(self):
        self.__assert_state_rules()

        if self.state is ReactorState.init:
            assert self.enable is False
            self.__log.info('Stopped.')
            self.__state = ReactorState.stopped
        elif self.state is ReactorState.name_resolution:
            if self.enable:
                # When resolution is complete
                self.__log.info('Stopping.')
                self.__enable = False
            else:
                self.__log.info('Stop request while already stopping.')
        elif self.state is ReactorState.connecting:
            if self.enable:
                self.__log.info('Stopping.')
                self.__enable = False
                self.__terminate(ReactorState.stopped, None)
            else:
                self.__log.info('Stop request while already stopping.')
        elif self.state is ReactorState.handshake:
            if self.enable:
                self.__log.info('Stopping.')
                self.__enable = False
                self.__terminate(ReactorState.stopped, None)
            else:
                self.__log.info('Stop request while already stopping.')
        elif self.state in (ReactorState.connack, ReactorState.connected):
            if self.enable:
                self.__log.info('Stopping.')
                self.__enable = False
                self.__preflight_queue.append(MqttDisconnect())
            else:
                self.__log.info('Stop request while already stopping.')
        # elif self.state is ReactorState.mute:
        #     self.__log.info('Stop.')
        elif self.state is ReactorState.stopped:
            assert self.enable is False
            self.__log.warning('Stop while already stopped.')
        elif self.state is ReactorState.error:
            assert self.enable is False
            self.__log.warning('Stop while already in error.')
        else:
            raise NotImplementedError(self.state)

        self.__assert_state_rules()
        self.__want_rw_update()

    def terminate(self):
        """When in an active state immediately shuts down any socket
        reading and writing, closes the socket, cancels all outstanding
        scheduler deadlines, puts the reactor into state
        ReactorState.stopped, then calls self.on_connect_fail
        (if in a connect/connack state) or alternatively
        self.on_disconnect if in some other active state.  When reactor
        is not in an inactive state this method has no effect.
        """
        self.__assert_state_rules()

        self.__log.info('Terminating.')

        if self.state in ACTIVE_STATES:
            self.__terminate(ReactorState.stopped)
        elif self.state in INACTIVE_STATES:
            pass
        else:
            raise NotImplementedError(self.state)

        self.__assert_state_rules()
        self.__want_rw_update()

    def want_read(self):
        """True if the reactor is ready to process incoming socket data;
        False otherwise.

        Returns
        -------
        bool
        """
        if self.state in ACTIVE_STATES:
            if self.state in (ReactorState.connecting, ReactorState.name_resolution):
                rv = False
            else:
                rv = True
        else:
            rv = False

        return rv

    def want_write(self):
        """True if the reactor is ready write data to the socket; False
        otherwise.

        Returns
        -------
        bool
        """
        if self.state in ACTIVE_STATES:
            if self.state is ReactorState.connecting:
                rv = True
            elif self.state is ReactorState.connack:
                rv = bool(self.__wbuf) or self.__ssl_want_write
            elif self.state is ReactorState.name_resolution:
                rv = False
            elif bool(self.__wbuf) or bool(self.__preflight_queue):
                rv = True
            else:
                rv = False or self.__ssl_want_write
        else:
            rv = False

        return rv

    def __decode_packet_body(self, header, num_header_bytes, packet_class):
        num_packet_bytes = num_header_bytes + header.remaining_len

        body = self.__rbuf[num_header_bytes:num_packet_bytes]
        num_body_bytes_consumed, packet = packet_class.decode_body(header, BytesReader(body))
        assert num_packet_bytes == num_header_bytes + num_body_bytes_consumed
        self.__rbuf = bytearray(self.__rbuf[num_packet_bytes:])
        return packet

    def __on_recv_bytes(self, new_bytes):
        assert len(new_bytes) > 0

        if self.state is not ReactorState.mute:
            if self.__keepalive_due_deadline is not None:
                self.__keepalive_due_deadline.cancel()
                self.__keepalive_due_deadline = None
            self.__keepalive_due_deadline = self.__scheduler.add(self.keepalive_period, self.__keepalive_due_timeout)

            self.__keepalive_abort_deadline.cancel()
            self.__keepalive_abort_deadline = self.__scheduler.add(1.5*self.keepalive_period,
                                                                   self.__keepalive_abort_timeout)

        self.__log.debug('Received %d bytes 0x%s', len(new_bytes), HexOnStr(new_bytes))
        self.__rbuf.extend(new_bytes)

        while True:
            num_header_bytes, header = MqttFixedHeader.decode(BytesReader(bytes(self.__rbuf)))
            num_packet_bytes = num_header_bytes + header.remaining_len
            if len(self.__rbuf) >= num_packet_bytes:
                if header.packet_type == MqttControlPacketType.connack:
                    self.__on_connack(self.__decode_packet_body(header, num_header_bytes, MqttConnack))
                elif header.packet_type == MqttControlPacketType.suback:
                    self.__on_suback(self.__decode_packet_body(header, num_header_bytes, MqttSuback))
                elif header.packet_type == MqttControlPacketType.puback:
                    self.__on_puback(self.__decode_packet_body(header, num_header_bytes, MqttPuback))
                elif header.packet_type == MqttControlPacketType.publish:
                    self.__on_publish(self.__decode_packet_body(header, num_header_bytes, MqttPublish))
                elif header.packet_type == MqttControlPacketType.pingresp:
                    self.__on_pingresp(self.__decode_packet_body(header, num_header_bytes, MqttPingresp))
                elif header.packet_type == MqttControlPacketType.pubrel:
                    self.__on_pubrel(self.__decode_packet_body(header, num_header_bytes, MqttPubrel))
                elif header.packet_type == MqttControlPacketType.pubcomp:
                    self.__on_pubcomp(self.__decode_packet_body(header, num_header_bytes, MqttPubcomp))
                elif header.packet_type == MqttControlPacketType.pubrec:
                    self.__on_pubrec(self.__decode_packet_body(header, num_header_bytes, MqttPubrec))
                else:
                    m = 'Received unsupported message type {}.'.format(header.packet_type)
                    self.__log.error(m)
                    self.__abort(DecodeReactorFail(m))

    def read(self):
        """Calls recv on underlying socket exactly once and returns the
        number of bytes read.  If the underlying socket does not return
        any bytes due to an error or exception then zero is returned and
        the reactor state is set to error.  A write call may be made to
        the underlying socket to flush any bytes queued as a result of
        servicing the read request.

        Returns
        -------
        int
            number of bytes read from socket.
        """
        self.__assert_state_rules()

        self.__ssl_want_write = False
        self.__ssl_want_read = False

        num_bytes_read = 0
        if self.state not in INACTIVE_STATES:
            if self.state is ReactorState.handshake:
                self.__set_handshake()
            else:
                try:
                    new_bytes = self.socket.recv(4096)
                    num_bytes_read = len(new_bytes)
                    if new_bytes:
                        self.__on_recv_bytes(new_bytes)
                    else:
                        self.__on_muted_remote()

                except UnderflowDecodeError:
                    # Not enough header bytes.
                    pass
                except DecodeError as e:
                    self.__log.error('Error decoding message (%s)', str(e))
                    self.__abort(DecodeReactorFail(str(e)))
                except ssl.SSLWantWriteError:
                    self.__ssl_want_write = True
                except ssl.SSLWantReadError:
                    self.__ssl_want_read = True
                except socket.error as e:
                    if e.errno == errno.EWOULDBLOCK:
                        # No write space ready.
                        pass
                    else:
                        self.__abort_socket_error(SocketReactorFail(e.errno))

        self.__assert_state_rules()
        self.__want_rw_update()
        return num_bytes_read

    def __on_connack_accepted(self, connack):
        # TODO: connack accepted only happens at certain times.
        if self.state in (ReactorState.connack, ReactorState.mute):
            if connack.session_present and self.clean_session:
                # [MQTT-3.2.2-1]
                self.__abort_protocol_violation('Server indicates a session is present when none was requested.')
            else:
                if self.state is ReactorState.connack:
                    self.__state = ReactorState.connected
                elif self.state is ReactorState.mute:
                    pass
                else:
                    raise NotImplementedError(self.state)

                if self.on_connack is not None:
                    self.on_connack(self, connack)

                self.__launch_next_queued_packet()
        else:
            raise NotImplementedError(self.state)

    def __on_connack(self, connack):
        """Called once when a connack packet is received.

        Parameters
        ----------
        connack: MqttConnack
        """
        # TODO: Can this method ever be reached while mute?
        if self.state in (ReactorState.connack, ReactorState.mute):
            self.__log.info('Received %s.', repr(connack))

            if connack.return_code == ConnackResult.accepted:
                # The first packet sent from the Server to the Client MUST
                # be a CONNACK Packet [MQTT-3.2.0-1].
                self.__on_connack_accepted(connack)
            elif connack.return_code == ConnackResult.fail_bad_protocol_version:
                self.__log.error('Connect failed: bad protocol version.')
                self.__abort(ConnectReactorFail(connack.return_code))
            elif connack.return_code == ConnackResult.fail_bad_client_id:
                self.__log.error('Connect failed: bad client ID.')
                self.__abort(ConnectReactorFail(connack.return_code))
            elif connack.return_code == ConnackResult.fail_server_unavailable:
                self.__log.error('Connect failed: server unavailable.')
                self.__abort(ConnectReactorFail(connack.return_code))
            elif connack.return_code == ConnackResult.fail_bad_username_or_password:
                self.__log.error('Connect failed: bad username or password.')
                self.__abort(ConnectReactorFail(connack.return_code))
            elif connack.return_code == ConnackResult.fail_not_authorized:
                self.__log.error('Connect failed: not authorized.')
                self.__abort(ConnectReactorFail(connack.return_code))
            else:
                raise NotImplementedError(connack.return_code)
        elif self.state is ReactorState.connected:
            self.__abort_protocol_violation('Received connack at an inappropriate time.')
        else:
            raise NotImplementedError(self.state)

    def __on_publish(self, publish):
        """Called when a publish packet is received from the remote.

        Parameters
        ----------
        publish: MqttPublish
        """
        if self.state is ReactorState.connected:
            self.__log.info('Received %s.', repr(publish))
            if self.on_publish is not None:
                self.on_publish(self, publish)

            if publish.qos == 0:
                pass
            elif publish.qos == 1:
                self.__preflight_queue.append(MqttPuback(publish.packet_id))
            elif publish.qos == 2:
                self.__preflight_queue.append(MqttPubrec(publish.packet_id))
                # TODO: Record publish packet
            else:
                raise NotImplementedError(publish.qos)
        # TODO: publish arrives while mute.
        # elif self.state is ReactorState.stopping:
        #     if publish.qos == 0:
        #         pass
        #     elif publish.qos == 1:
        #         self.__log.info('Receiving %s but not sending puback because client is stopping.', repr(publish))
        #     elif publish.qos == 2:
        #         raise NotImplementedError()
        #
        #     if self.on_publish is not None:
        #         self.on_publish(self, publish)
        else:
            raise NotImplementedError(self.state)

    def __on_suback(self, suback):
        """Called when a suback packet is received from remote.

        Parameters
        ----------
        suback: MqttSuback
        """
        if self.state is ReactorState.connected:
            idx = index(self.__inflight_queue,
                        lambda p: p.packet_type == MqttControlPacketType.subscribe and p.packet_id == suback.packet_id)
            if idx is None:
                subscribe = None
            else:
                subscribe = self.__inflight_queue[idx]

            if subscribe is None:
                self.__abort_protocol_violation('Received %s for a mid that is not in-flight; aborting.',
                                                repr(suback))
            else:
                if len(suback.results) == len(subscribe.topics):
                    self.__log.info('Received %s.', repr(suback))
                    subscribe._set_status(MqttSubscribeStatus.done)

                    self.__send_packet_ids.remove(subscribe.packet_id)
                    del self.__inflight_queue[idx]

                    if self.on_suback is not None:
                        self.on_suback(self, suback)
                else:
                    m = 'Received %s as a response to %s, but the number of subscription' \
                        ' results does not equal the number of subscription requests; aborting.'
                    self.__abort_protocol_violation(m,
                                                    repr(suback),
                                                    repr(subscribe.packet()))
        else:
            raise NotImplementedError(self.state)

    def __on_puback(self, puback):
        """Called when a puback packet is received from the remote.

        Parameters
        ----------
        puback: MqttPuback

        """
        if self.state in (ReactorState.connected, ReactorState.mute):
            idx = index(self.__inflight_queue, lambda p: p.packet_type is MqttControlPacketType.publish)
            if idx is None:
                publish = None
            else:
                publish = self.__inflight_queue[idx]

            in_flight_packet_ids = [p.packet_id for p in self.__inflight_queue if hasattr(p, 'packet_id')]
            if publish and publish.packet_id == puback.packet_id:
                if publish.qos == 1:
                    del self.__inflight_queue[idx]
                    self.__send_packet_ids.remove(publish.packet_id)
                    self.__log.info('Received %s.', repr(puback))
                    publish._set_status(MqttPublishStatus.done)

                    if self.on_puback is not None:
                        self.on_puback(self, puback)
                else:
                    self.__abort_protocol_violation('Received %s, an inappropriate response to qos=%d %s; aborting.',
                                                    ReprOnStr(puback),
                                                    publish.qos,
                                                    ReprOnStr(publish))
            elif publish and puback.packet_id in in_flight_packet_ids:
                m = 'Received %s instead of puback for next-in-flight packet_id=%d; aborting.'
                self.__abort_protocol_violation(m,
                                                ReprOnStr(puback),
                                                publish.packet_id)
            else:
                m = 'Received %s when packet_id=%d was not in-flight; aborting.'
                self.__abort_protocol_violation(m,
                                                ReprOnStr(puback),
                                                puback.packet_id)
        else:
            raise NotImplementedError(self.state)

    def __on_pubrec(self, pubrec):
        """

        Parameters
        ----------
        pubrec: MqttPubrec
        """
        if self.state is ReactorState.connected:
            idx = index(self.__inflight_queue, lambda p: p.packet_type is MqttControlPacketType.publish)
            if idx is None:
                publish_ticket = None
            else:
                publish_ticket = self.__inflight_queue[idx]

            in_flight_packet_ids = [p.packet_id for p in self.__inflight_queue]
            if publish_ticket and publish_ticket.packet_id == pubrec.packet_id:
                if publish_ticket.qos == 2:
                    del self.__inflight_queue[idx]
                    self.__log.info('Received %s.', repr(pubrec))

                    insert_idx = len(self.__preflight_queue)
                    if self.on_pubrec is not None:
                        self.on_pubrec(self, pubrec)

                    self.__preflight_queue.insert(insert_idx, MqttPubrel(pubrec.packet_id))
                else:
                    publish = MqttPublish(publish_ticket.packet_id,
                                          publish_ticket.topic,
                                          publish_ticket.payload,
                                          publish_ticket.dupe,
                                          publish_ticket.qos,
                                          publish_ticket.retain)
                    self.__abort_protocol_violation('Received unexpected %s in response to qos=%d publish %s; aborting.',
                                                    ReprOnStr(pubrec),
                                                    publish_ticket.qos,
                                                    ReprOnStr(publish))
            elif publish_ticket and pubrec.packet_id in in_flight_packet_ids:
                m = 'Received unexpected %s when packet_id=%d was next-in-flight; aborting.'
                self.__abort_protocol_violation(m,
                                                ReprOnStr(pubrec),
                                                publish_ticket.packet_id)
            else:
                m = 'Received unexpected %s when packet_id=%d was not in-flight; aborting.'
                self.__abort_protocol_violation(m,
                                                ReprOnStr(pubrec),
                                                pubrec.packet_id)
        else:
            raise NotImplementedError(self.state)

    def __on_pubcomp(self, pubcomp):
        """

        Parameters
        ----------
        pubcomp: MqttPubcomp

        """
        if self.state is ReactorState.connected:
            idx = index(self.__inflight_queue, lambda p: p.packet_type is MqttControlPacketType.pubrel)
            if idx is None:
                pubrel = None
            else:
                pubrel = self.__inflight_queue[idx]

            in_flight_pubrel_packet_ids = [p.packet_id for p in self.__inflight_queue if p.packet_type is MqttControlPacketType.pubrel]
            if pubrel and pubrel.packet_id == pubcomp.packet_id:
                del self.__inflight_queue[idx]
                self.__log.info('Received %s.', repr(pubcomp))

                if self.on_pubcomp is not None:
                    self.on_pubcomp(self, pubcomp)
            elif pubrel and pubcomp.packet_id in in_flight_pubrel_packet_ids:
                m = 'Received %s when packet_id=%d was the next pubrel in flight; aborting.'
                self.__abort_protocol_violation(m,
                                                ReprOnStr(pubcomp),
                                                pubrel.packet_id)
            else:
                m = 'Received %s when no pubrel for packet_id=%d was in-flight; aborting.'
                self.__abort_protocol_violation(m,
                                                ReprOnStr(pubcomp),
                                                pubcomp.packet_id)
        else:
            raise NotImplementedError(self.state)

    def __on_pubrel(self, pubrel):
        """

        Parameters
        ----------
        pubrel: MqttPubrel

        """
        if self.state is ReactorState.connected:
            self.__log.info('Received %s.', repr(pubrel))
            if self.on_pubrel is not None:
                self.on_pubrel(self, pubrel)
            self.__preflight_queue.append(MqttPubcomp(pubrel.packet_id))
        else:
            raise NotImplementedError(self.state)

    def __on_pingresp(self, pingresp):
        """

        Parameters
        ----------
        pingresp: MqttPingresp
        """
        if self.state is ReactorState.connected:
            self.__log.info('Received %s.', repr(pingresp))
        else:
            raise NotImplementedError(self.state)

    def __on_muted_remote(self):
        if self.state in (ReactorState.connack, ReactorState.connected):
            self.__log.warning('Remote closed stream unexpectedly.')
            self.__abort(MutePeerReactorFail())
        elif self.state is ReactorState.mute:
            self.__log.info('Remote gracefully closed stream.')
            self.__terminate(ReactorState.stopped, None)
        else:
            raise NotImplementedError(self.state)

    def __launch_preflight_packets(self):
        """Takes messages from the preflight_queue and places them in
        the in_flight_queues.

        Simple launch process, but very inefficient!  Recommend
        improvements based on benchmarks.

        Returns
        -------
        int
            Returns number of bytes flushed to output buffers.
        """

        # Prepare bytes for launch
        # TODO: must be larger than largest MQTT packet size
        max_buf_size = 2**16
        wbuf_size = len(self.__wbuf)

        #**************************************
        #
        #           0 1 2 3 4 5 6 7 8
        #  -----------x|----x|----x|
        #
        # packet_end_offset = [1, 4, 7]
        #
        packet_end_offsets = [wbuf_size]
        bio = BytesIO()
        num_new_bytes = 0
        for packet_record in self.__preflight_queue:
            num_bytes_encoded = packet_record.encode(bio)
            if wbuf_size + num_bytes_encoded <= max_buf_size:
                wbuf_size += num_bytes_encoded
                num_new_bytes += num_bytes_encoded
                packet_end_offsets.append(wbuf_size)
            else:
                break

        # Write as many bytes as possible.
        self.__wbuf.extend(bio.getvalue()[0:num_new_bytes])
        num_bytes_flushed = self.__flush()

        # Mark launched messages as in-flight.
        num_messages_launched = 0
        for packet_end_offset in packet_end_offsets:
            if num_bytes_flushed > packet_end_offset:
                num_messages_launched += 1
            else:
                break

        launched_packets = self.__preflight_queue[0:num_messages_launched]
        del self.__preflight_queue[0:num_messages_launched]

        for packet_record in launched_packets:
            packet = packet_record

            self.__log.info('Launching message %s.', repr(packet.packet()))

            # if packet.packet_type is MqttControlPacketType.connect:
            #     pass
            # elif packet.packet_type is MqttControlPacketType.connack:
            #     pass
            if packet_record.packet_type is MqttControlPacketType.publish:
                if packet_record.qos == 0:
                    self.__send_packet_ids.remove(packet_record.packet_id)
                    packet_record._set_status(MqttPublishStatus.done)
                elif packet_record.qos == 1:
                    packet_record._set_status(MqttPublishStatus.puback)
                    self.__inflight_queue.append(packet_record)
                elif packet_record.qos == 2:
                    packet_record._set_status(MqttPublishStatus.pubrec)
                    self.__inflight_queue.append(packet_record)
                else:
                    raise NotImplementedError(packet_record.qos)
            # elif packet.packet_type is MqttControlPacketType.puback:
            #     pass
            # elif packet.packet_type is MqttControlPacketType.pubrec:
            #     pass
            elif packet_record.packet_type is MqttControlPacketType.pubrel:
                self.__inflight_queue.append(packet_record)
            # elif packet.packet_type is MqttControlPacketType.pubcomp:
            #     pass
            elif packet_record.packet_type is MqttControlPacketType.subscribe:
                packet_record._set_status(MqttSubscribeStatus.ack)
                self.__inflight_queue.append(packet_record)
            # elif packet.packet_type is MqttControlPacketType.suback:
            #     pass
            elif packet_record.packet_type is MqttControlPacketType.unsubscribe:
                self.__inflight_queue.append(packet_record)
            # elif packet.packet_type is MqttControlPacketType.unsuback:
            #     pass
            # elif packet.packet_type is MqttControlPacketType.pingreq:
            #     pass
            # elif packet.packet_type is MqttControlPacketType.pingresp:
            #     pass
            elif packet.packet_type is MqttControlPacketType.disconnect:
                assert self.enable is False
                self.__log.info('Shutting down outgoing stream.')
                self.__inflight_queue.append(packet_record)
                self.socket.shutdown(socket.SHUT_WR)
                self.__state = ReactorState.mute

                if self.__keepalive_due_deadline is not None:
                    self.__keepalive_due_deadline.cancel()
                    self.__keepalive_due_deadline = None

                assert self.__keepalive_abort_deadline is not None

        if num_bytes_flushed:
            self.__log.debug('Wrote %d bytes 0x%s.', num_bytes_flushed, HexOnStr(self.__wbuf[0:num_bytes_flushed]))
            self.__wbuf = self.__wbuf[num_bytes_flushed:]

        return num_bytes_flushed

    def __launch_next_queued_packet(self):
        """Takes messages from the preflight_queue and places them in
        the in_flight_queues.

        Takes messages from the in_flight_queues in the order they
        appear in the preflight_queues.

        Returns
        -------
        int
            Returns number of bytes flushed to output buffers.
        """

        if self.state in (ReactorState.init, ReactorState.stopped, ReactorState.error):
            num_bytes_flushed = 0
        elif self.state in (ReactorState.connack, ReactorState.connected):
            num_bytes_flushed = self.__launch_preflight_packets()
        elif self.state is ReactorState.mute:
            num_bytes_flushed = 0
        else:
            raise NotImplementedError(self.state)

        return num_bytes_flushed

    def __set_connack(self):
        assert not self.__inflight_queue
        assert not self.__wbuf

        self.__state = ReactorState.connack

        connect = MqttConnect(self.client_id, self.clean_session, self.keepalive_period,
                              username=self.__username,
                              password=self.__password)
        self.__preflight_queue.insert(0, connect)
        self.__launch_next_queued_packet()

    def __set_handshake(self):
        self.__state = ReactorState.handshake
        self.__ssl_want_read = False
        self.__ssl_want_write = False

        try:
            self.socket.do_handshake()
            self.__set_connack()
        except ssl.SSLWantReadError:
            self.__ssl_want_read = True
        except ssl.SSLWantWriteError:
            self.__ssl_want_write = True

    def __on_connect(self):
        """Called when a socket becomes connected; reactor must be in
        the `ReactorState.connecting` state."""
        assert self.state == ReactorState.connecting

        self.__log.info('Connected.')
        self.__keepalive_abort_deadline = self.__scheduler.add(1.5*self.keepalive_period,
                                                               self.__keepalive_abort_timeout)

        if hasattr(self.socket, 'do_handshake'):
            self.__set_handshake()
        else:
            self.__set_connack()

    def __flush(self):
        """Calls send exactly once; returning the number of bytes written.

        Returns
        -------
        int
            Number of bytes written.
        """

        self.__ssl_want_read = False
        self.__ssl_want_write = False

        num_bytes_written = 0
        if self.__wbuf:
            try:
                num_bytes_written = self.socket.send(self.__wbuf)
            except ssl.SSLWantReadError:
                self.__ssl_want_read = True
            except ssl.SSLWantWriteError:
                self.__ssl_want_write = True
            except socket.error as e:
                if e.errno == errno.EWOULDBLOCK:
                    # No write space ready.
                    pass
                elif e.errno == errno.EPIPE:
                    self.__log.error("Remote unexpectedly closed the connection (<%s: %d>); Aborting.",
                                     errno.errorcode[e.errno],
                                     e.errno)
                    self.__abort(SocketReactorFail(e.errno))
                else:
                    self.__abort_socket_error(SocketReactorFail(e.errno))

        return num_bytes_written

    def __terminate(self, state, error=None):
        """

        Parameters
        ----------
        state: ReactorState
        error: ReactorFail
        """

        self.__enable = False
        if self.state in ACTIVE_STATES:
            if self.state in (ReactorState.name_resolution, ReactorState.connecting, ReactorState.handshake, ReactorState.connack):
                on_disconnect_cb = self.on_connect_fail
            elif self.state in (ReactorState.connected, ReactorState.mute):
                on_disconnect_cb = self.on_disconnect
            else:
                raise NotImplementedError(self.state)

            if self.socket is not None:
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except socket.error as e:
                    if e.errno == errno.ENOTCONN:
                        pass
                    else:
                        raise
                self.socket.close()
        else:
            on_disconnect_cb = None

        self.__wbuf = bytearray()
        self.__rbuf = bytearray()

        if self.__keepalive_abort_deadline is not None:
            self.__keepalive_abort_deadline.cancel()
            self.__keepalive_abort_deadline = None

        if self.__keepalive_due_deadline is not None:
            self.__keepalive_due_deadline.cancel()
            self.__keepalive_due_deadline = None

        self.__state = state
        self.__error = error

        if callable(on_disconnect_cb):
            on_disconnect_cb(self)

    def __abort_socket_error(self, se):
        """

        Parameters
        ----------
        se: SocketReactorFail
        """
        self.__log.error('%s (<%s: %d>).  Aborting.',
                         os.strerror(se.errno),
                         errno.errorcode[se.errno],
                         se.errno)
        self.__abort(se)

    def __abort_protocol_violation(self, m, *params):
        self.__log.error(m, *params)
        self.__abort(ProtocolReactorFail(m % params))

    def __abort(self, e):
        self.__terminate(ReactorState.error, e)

    def __keepalive_due_timeout(self):
        self.__assert_state_rules()
        assert self.__keepalive_due_deadline is not None

        assert self.state in (
            ReactorState.connack,
            ReactorState.connected,
        )

        self.__preflight_queue.append(MqttPingreq())
        self.__keepalive_due_deadline = None

        self.__assert_state_rules()
        self.__want_rw_update()

    def __keepalive_abort_timeout(self):
        self.__assert_state_rules()

        assert self.__keepalive_due_deadline is None
        assert self.__keepalive_abort_deadline is not None

        if self.state in (
                ReactorState.handshake,
                ReactorState.connack,
                ReactorState.connected,
                ReactorState.mute):

            msg = "More than abort period (%.01fs) has passed since last bytes received.  Aborting."
            self.__log.warning(msg, self.keepalive_timeout_period)
        else:
            raise NotImplementedError(self.state)

        self.__keepalive_abort_deadline = None

        self.__abort(KeepaliveTimeoutReactorFail())

        self.__assert_state_rules()
        self.__want_rw_update()

    def write(self):
        """If there is any data queued to be written to the underlying
        socket then a single call to socket send will be made to try
        and flush it to the socket write buffer.

        If self.state is an inactive state then no action is taken."""
        self.__assert_state_rules()

        if self.state in ACTIVE_STATES:
            if self.state == ReactorState.connecting:
                e = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if e == 0:
                    self.__on_connect()
                elif errno.EINPROGRESS:
                    pass
                else:
                    self.__abort_socket_error(SocketReactorFail(e.errno))
            elif self.state is ReactorState.handshake:
                self.__set_handshake()
            elif self.state in (ReactorState.connack, ReactorState.connected):
                self.__launch_next_queued_packet()
            else:
                raise NotImplementedError(self.state)
        elif self.state in INACTIVE_STATES:
            pass
        else:
            raise NotImplementedError(self.state)

        self.__assert_state_rules()
        self.__want_rw_update()
