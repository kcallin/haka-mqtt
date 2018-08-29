import errno
import socket
import logging
from binascii import b2a_hex
from io import BytesIO
from itertools import cycle

from enum import (
    IntEnum,
    unique,
)

from haka_mqtt.clock import SystemClock
from haka_mqtt.mqtt import (
    MqttConnect,
    MqttSubscribe,
    MqttFixedHeader,
    MqttControlPacketType,
    MqttConnack,
    MqttSuback,
    UnderflowDecodeError,
    DecodeError,
    MqttPublish,
    MqttPuback,
    MqttDisconnect, MqttPingreq, MqttPingresp, MqttPubrec, MqttPubrel, MqttPubcomp, ConnackResult)
from haka_mqtt.on_str import HexOnStr


class ReactorProperties(object):
    """
    Attributes
    ----------
    socket: socket.socket
    client_id: str
    clock:
    keepalive_period: int
        0 <= keepalive_period <= 2*16-1
    clean_session: bool
        With clean session set to True reactor will clear all message
        buffers on disconnect without regard to QoS; otherwise
        unacknowledged messages will be retransmitted after a
        re-connect.
    max_inflight_publish: int
        Maximum number of in-flight publish messages.
    """
    def __init__(self):
        self.socket = None
        self.endpoint = None
        self.client_id = None
        self.clock = SystemClock()
        self.keepalive_period = 10*60
        self.scheduler = None
        self.clean_session = True
        self.max_inflight_publish = 1


@unique
class ReactorState(IntEnum):
    init = 0
    connecting = 1
    connack = 2
    connected = 3
    stopping = 4
    stopped = 5
    error = 6


# States where there are no active deadlines, the socket is closed and there
# is no active I/O.
#
INACTIVE_STATES = (ReactorState.init, ReactorState.stopped, ReactorState.error)


class TopicSubscription(object):
    def __init__(self):
        pass


class ReactorError:
    pass


class MqttConnectFail(ReactorError):
    def __init__(self, result):
        assert result != ConnackResult.accepted
        self.result = result

    def __eq__(self, other):
        return self.result == other.result


class ProtocolViolationReactorError(ReactorError):
    def __init__(self, desc):
        self.description = desc

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, self.description)


class KeepaliveTimeoutReactorError(ReactorError):
    def __eq__(self, other):
        return isinstance(other, KeepaliveTimeoutReactorError)


class SocketError(ReactorError):
    """
    Attributes
    ----------
    error: errno
    """
    def __init__(self, errno_val):
        """
        Parameters
        ----------
        errno_val: int
        """
        assert errno_val in errno.errorcode

        self.errno = errno_val

    def __repr__(self):
        return 'SocketError({}<{}>)'.format(errno.errorcode[self.errno], self.errno)


class AddressingReactorError(ReactorError):
    """
    Attributes
    ----------
    errno: int
    description: str
    """
    def __init__(self, gaierror):
        """
        Parameters
        ----------
        errno: socket.gaierror
        """
        assert isinstance(gaierror, socket.gaierror)
        self.__errno = gaierror.errno
        self.__desc = gaierror.strerror

    @property
    def errno(self):
        return self.__errno

    @property
    def description(self):
        return self.__desc

    def __repr__(self):
        return '{}({} ({}))'.format(self.__class__.__name__, self.errno, self.description)


class DecodeReactorError(ReactorError):
    def __init__(self, description):
        self.description = description


class ProtocolViolationError(ReactorError):
    def __init__(self, description):
        self.description = description


class Reactor:
    def __init__(self, properties):
        """

        Parameters
        ----------
        properties: ReactorProperties
        """

        assert properties.client_id is not None
        assert properties.socket is not None
        assert properties.endpoint is not None
        assert properties.scheduler is not None
        assert 0 <= properties.keepalive_period <= 2**16-1
        assert isinstance(properties.max_inflight_publish, int)
        assert properties.max_inflight_publish >= 1
        assert isinstance(properties.keepalive_period, int)
        assert isinstance(properties.clean_session, bool)

        self.__log = logging.getLogger('mqtt_reactor')
        self.__wbuf = bytearray()
        self.__rbuf = bytearray()

        self.__client_id = properties.client_id
        self.__clock = properties.clock
        self.__keepalive_period = properties.keepalive_period
        self.__keepalive_due_deadline = None
        self.__keepalive_abort_deadline = None
        self.__last_poll_instant = None
        self.__clean_session = properties.clean_session
        self.__max_inflight_publish = properties.max_inflight_publish

        self.socket = properties.socket
        self.endpoint = properties.endpoint
        self.__packet_id_iter = cycle(xrange(0, 2**16-1))
        self.__state = ReactorState.init
        self.__error = None

        self.__queue = []
        self.__in_flight_publish = []
        self.__in_flight_packets = {}

        self.__ping_active = False
        self.__scheduler = properties.scheduler

        self.on_puback = None
        self.on_suback = None
        self.on_connack = None
        self.on_publish = None
        self.on_pubrel = None
        self.on_pubcomp = None
        self.on_pubrec = None

    @property
    def clean_session(self):
        return self.__clean_session

    @property
    def max_inflight_publish(self):
        """
        Returns
        -------
        int
            Maximum number of in-flight publish messages.
        """
        return self.__max_inflight_publish

    @property
    def client_id(self):
        return self.__client_id

    @property
    def last_poll_instant(self):
        return self.__last_poll_instant

    @property
    def keepalive_period(self):
        return self.__keepalive_period

    @property
    def keepalive_timeout_period(self):
        return self.keepalive_period * 1.5

    @property
    def error(self):
        """

        Returns
        -------
        ReactorError or None
        """
        return self.__error

    @property
    def state(self):
        """

        Returns
        -------
        ReactorState
        """
        return self.__state

    def __assert_state_rules(self):
        if self.state in INACTIVE_STATES:
            assert self.__keepalive_due_deadline is None
            assert self.__keepalive_abort_deadline is None
            assert not self.want_write()
            assert not self.want_write()

            # TODO: assert socket is not running.

        if self.state is ReactorState.error:
            assert self.error is not None

    def subscribe(self, topics):
        """

        Parameters
        ----------
        topics: iterable of MqttTopic
        """
        assert self.state == ReactorState.connected
        subscribe = MqttSubscribe(self.__packet_id_iter.next(), topics)
        self.__in_flight_packets[subscribe.packet_id] = subscribe
        self.__queue_and_flush(subscribe)

    def unsubscribe(self, topics):
        pass

    def publish(self, topic, payload, qos, retain=False):
        """
        Parameters
        ----------
        topic: str
        payload: bytes
        qos: int
            0 <= qos <= 2
        retain: False

        Return
        ------
        MqttPublish
        """
        self.__assert_state_rules()
        assert 0 <= qos <= 2
        assert self.state is ReactorState.connected

        p = MqttPublish(next(self.__packet_id_iter), topic, payload, False, qos, retain)
        self.__queue_and_flush(p)

        self.__assert_state_rules()

        return p

    def __start(self):
        assert self.state in INACTIVE_STATES
        self.__error = None

        self.__log.info('Starting.')
        in_flight_packets = list(self.__in_flight_publish)
        self.__queue = in_flight_packets + [p for p in self.__queue if p.packet_type is MqttControlPacketType.publish]
        self.__wbuf = bytearray()
        self.__rbuf = bytearray()

        try:
            self.__state = ReactorState.connecting
            self.socket.connect(self.endpoint)
            self.__on_connect()
        except socket.gaierror as e:
            self.__log.error('%s (errno=%d).  Aborting.', e.strerror, e.errno)
            self.__abort(AddressingReactorError(e))
        except socket.error as e:
            if e.errno == errno.EINPROGRESS:
                # Connection in progress.
                self.__log.info('Connecting.')
            else:
                self.__log.error('%s (errno=%d).  Aborting.', e.strerror, e.errno)
                self.__abort(SocketError(e.errno))

    def start(self):
        self.__assert_state_rules()

        if self.state in INACTIVE_STATES:
            self.__start()
        else:
            self.__log.warning("Start called while already running!")

        self.__assert_state_rules()

    def stop(self):
        self.__assert_state_rules()
        if self.state is ReactorState.connected:
            self.__log.info('Stopping.')
            if not self.__in_flight_packets:
                self.__queue_and_flush(MqttDisconnect())

                if not self.__wbuf:
                    self.__log.info('Shutting down outgoing stream.')
                    self.socket.shutdown(socket.SHUT_WR)

                # Stop keepalive messages.
                # TODO: What if remote socket takes forever to close?

            self.__state = ReactorState.stopping
        else:
            raise NotImplementedError()

        self.__assert_state_rules()

    def terminate(self):
        self.__assert_state_rules()

        self.__log.info('Terminating.')

        if self.state not in INACTIVE_STATES:
            self.__terminate()

        self.__state = ReactorState.stopped

        self.__assert_state_rules()

    def want_read(self):
        return self.state in (ReactorState.connack, ReactorState.connected, ReactorState.stopping)

    def want_write(self):
        return bool(self.__wbuf) or self.state == ReactorState.connecting

    def __decode_packet_body(self, header, num_header_bytes, packet_class):
        num_packet_bytes = num_header_bytes + header.remaining_len

        body = self.__rbuf[num_header_bytes:]
        num_body_bytes_consumed, packet = packet_class.decode_body(header, body)
        assert num_packet_bytes == num_header_bytes + num_body_bytes_consumed
        self.__rbuf = bytearray(self.__rbuf[num_packet_bytes:])
        return packet

    def __on_recv_bytes(self, new_bytes):
        assert len(new_bytes) > 0

        if self.__keepalive_due_deadline is not None:
            self.__keepalive_due_deadline.cancel()
            self.__keepalive_due_deadline = None
        self.__keepalive_due_deadline = self.__scheduler.add(self.keepalive_period, self.__keepalive_due_timeout)

        self.__keepalive_abort_deadline.cancel()
        self.__keepalive_abort_deadline = self.__scheduler.add(1.5*self.keepalive_period, self.__keepalive_abort_timeout)

        self.__log.debug('Received %d bytes 0x%s', len(new_bytes), HexOnStr(new_bytes))
        self.__rbuf.extend(new_bytes)

        while True:
            num_header_bytes, header = MqttFixedHeader.decode(self.__rbuf)
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
                else:
                    m = 'Received unsupported message type {}.'.format(header.packet_type)
                    self.__log.error(m)
                    self.__abort(DecodeReactorError(m))

    def read(self):
        """Calls recv on underlying socket exactly once and returns the
        number of bytes read.  If the underlying socket does not return
        any bytes due to an error or exception then zero is returned and
        the reactor state is set to error.

        Returns
        -------
        int
            number of bytes read from socket.
        """
        self.__assert_state_rules()

        num_bytes_read = 0
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
            self.__abort(DecodeReactorError(str(e)))
        except socket.error as e:
            if e.errno == errno.EWOULDBLOCK:
                # No write space ready.
                pass
            else:
                self.__log.error('While reading socket, %s (errno=%d).  Aborting.', e.strerror, e.errno)
                self.__abort(SocketError(e.errno))

        self.__assert_state_rules()
        return num_bytes_read

    def __on_connack_accepted(self, connack):
        if connack.session_present and self.clean_session:
            # [MQTT-3.2.2-1]
            e = ProtocolViolationReactorError('Server indicates a session is present when none was requested.')
            self.__log.error(e.description)
            self.__abort(e)
        else:
            if self.on_connack is not None:
                self.on_connack(self, connack)

            if self.__queue:
                self.__queue_and_flush(self.__queue[0])

    def __on_connack(self, connack):
        """

        Parameters
        ----------
        connack: MqttConnack
        """
        if self.state is ReactorState.connack:
            self.__log.info('Received %s.', repr(connack))
            self.__state = ReactorState.connected

            if connack.return_code == ConnackResult.accepted:
                # The first packet sent from the Server to the Client MUST
                # be a CONNACK Packet [MQTT-3.2.0-1].
                self.__on_connack_accepted(connack)
            elif connack.return_code == ConnackResult.fail_bad_protocol_version:
                self.__log.error('Bad protocol version; connect failed.')
                self.__abort(MqttConnectFail(connack.return_code))
            elif connack.return_code == ConnackResult.fail_bad_client_id:
                self.__log.error('Bad client ID; connect failed.')
                self.__abort(MqttConnectFail(connack.return_code))
            elif connack.return_code == ConnackResult.fail_server_unavailable:
                self.__log.error('Server unavailable; connect failed.')
                self.__abort(MqttConnectFail(connack.return_code))
            elif connack.return_code == ConnackResult.fail_bad_username_or_password:
                self.__log.error('Bad username or password; connect failed.')
                self.__abort(MqttConnectFail(connack.return_code))
            elif connack.return_code == ConnackResult.fail_not_authorized:
                self.__log.error('Not authorized; connect failed.')
                self.__abort(MqttConnectFail(connack.return_code))
            else:
                assert False
        else:
            m = 'Received connack at an inappropriate time.'
            self.__log.error(m)
            self.__abort(DecodeReactorError(m))

    def __on_publish(self, publish):
        """

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
                self.__queue_and_flush(MqttPuback(publish.packet_id))
            elif publish.qos == 2:
                self.__queue_and_flush(MqttPubrec(publish.packet_id))
                # TODO: Record publish packet
                # raise NotImplementedError()
        elif self.state is ReactorState.stopping:
            if publish.qos == 0:
                pass
            elif publish.qos == 1:
                self.__log.info('Receiving %s but not sending puback because client is stopping.', repr(publish))
            elif publish.qos == 2:
                raise NotImplementedError()

            if self.on_publish is not None:
                self.on_publish(self, publish)
        else:
            assert False, 'Received MqttSuback at an inappropriate time.'

    def __on_suback(self, suback):
        """

        Parameters
        ----------
        suback: MqttSuback

        """
        if self.state is ReactorState.connected:
            try:
                self.__in_flight_packets.pop(suback.packet_id)
                in_flight = True
            except KeyError:
                in_flight = False

            if in_flight:
                self.__log.info('Received %s.', repr(suback))
                if self.on_suback is not None:
                    self.on_suback(self, suback)
            else:
                self.__log.warning('Received %s for a mid that is not in-flight; aborting.', repr(suback))
                self.__abort(DecodeReactorError())
        else:
            assert False, 'Received MqttSuback at an inappropriate time.'

    def __on_puback(self, puback):
        """

        Parameters
        ----------
        suback: MqttPuback

        """
        if self.state is ReactorState.connected:
            try:
                publish = self.__in_flight_publish[0]
            except IndexError:
                publish = None

            if publish:
                if publish.packet_id == puback.packet_id:
                    if publish.qos == 1:
                        del self.__in_flight_publish[0]
                        self.__log.info('Received %s.', repr(puback))

                        if self.on_puback is not None:
                            self.on_puback(self, puback)
                    else:
                        self.__log.warning('Received %s in response to qos=1 publish %s; aborting.',
                                           repr(puback),
                                           repr(publish))
                        self.__abort(DecodeReactorError())
                else:
                    in_flight_mids = [publish.mid for publish in self.__in_flight_publish]
                    if puback.packet_id in in_flight_mids:
                        m = 'Received puback for mid=%d when mid=%d was expected;' \
                            ' mid=%d was not next in-flight; aborting.'
                        self.__abort_protocol_violation(m,
                                                        puback.packet_id,
                                                        publish.packet_id,
                                                        puback.packet_id)
                    else:
                        m = 'Received puback for mid=%d when mid=%d was expected;' \
                            ' mid=%d was not in-flight; aborting.'
                        self.__abort_protocol_violation(m,
                                                        puback.packet_id,
                                                        publish.packet_id,
                                                        puback.packet_id)
            else:
                self.__abort_protocol_violation('Received %s for a publish that was not in-flight; aborting.',
                                                repr(puback))
        else:
            assert False, 'Received MqttPuback at an inappropriate time.'

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
            self.__queue_and_flush(MqttPubcomp(pubrel.packet_id))
        else:
            assert False, 'Received MqttPubrel at an inappropriate time.'

    def __on_pingresp(self, pingresp):
        """

        Parameters
        ----------
        pingresp: MqttPingresp

        """
        if self.state is ReactorState.connected:
            self.__log.info('Received %s.', repr(pingresp))
        else:
            assert False, 'Received MqttSuback at an inappropriate time.'

    def __on_muted_remote(self):
        if self.state in (ReactorState.connack, ReactorState.connected):
            self.__log.warning('Remote closed stream unexpectedly.')
            self.__abort(DecodeReactorError('Remote closed unexpectedly.'))
        elif self.state in (ReactorState.stopping,):
            if len(self.__rbuf) > 0:
                self.__log.warning('While stopping remote closed stream in the middle of a packet transmission with 0x%s still in the buffer.', b2a_hex(self.__rbuf))
            elif len(self.__wbuf) > 0:
                self.__log.warning('While stopping remote closed stream before consuming bytes.')
            else:
                self.__log.info('Remote gracefully closed stream.')

            if self.__keepalive_due_deadline is not None:
                self.__keepalive_due_deadline.cancel()
                self.__keepalive_due_deadline = None

            if self.__keepalive_abort_deadline is not None:
                self.__keepalive_abort_deadline.cancel()
                self.__keepalive_abort_deadline = None

            self.socket.close()
            self.__state = ReactorState.stopped
        else:
            assert False, 'Received muted_remote at an inappropriate time.'

    def __launch_next_queued_packet(self):
        if self.__queue:
            packet = self.__queue.pop(0)

            # if packet.packet_type is MqttControlPacketType.connect:
            #     pass
            # elif packet.packet_type is MqttControlPacketType.connack:
            #     pass
            if packet.packet_type is MqttControlPacketType.publish:
                self.__in_flight_publish.append(packet)
            elif packet.packet_type is MqttControlPacketType.puback:
                pass
            elif packet.packet_type is MqttControlPacketType.pubrec:
                pass
            elif packet.packet_type is MqttControlPacketType.pubrel:
                pass
            elif packet.packet_type is MqttControlPacketType.pubcomp:
                pass
            elif packet.packet_type is MqttControlPacketType.subscribe:
                pass
            # elif packet.packet_type is MqttControlPacketType.suback:
            #     pass
            elif packet.packet_type is MqttControlPacketType.unsubscribe:
                pass
            elif packet.packet_type is MqttControlPacketType.unsuback:
                pass
            elif packet.packet_type is MqttControlPacketType.pingreq:
                pass
            elif packet.packet_type is MqttControlPacketType.pingresp:
                pass
            elif packet.packet_type is MqttControlPacketType.disconnect:
                pass

            self.__log.info('Launching message %s.', repr(packet))
            bio = BytesIO()
            packet.encode(bio)
            buf = bio.getvalue()
            self.__log.debug('Writing %d bytes 0x%s.', len(buf), HexOnStr(buf))
            self.__wbuf.extend(buf)
            num_bytes_flushed = self.__flush()
        else:
            num_bytes_flushed = 0

        return num_bytes_flushed

    def __queue_and_flush(self, packet):
        """

        Parameters
        ----------
        packet

        Returns
        -------
        int
            Returns number of bytes flushed to underlying socket.
        """
        self.__queue.append(packet)

        if self.__wbuf:
            num_bytes_flushed = 0
            self.__log.info('Queuing %s for delivery.', repr(packet))
        else:
            num_bytes_flushed = self.__launch_next_queued_packet()

        return num_bytes_flushed

    def __on_connect(self):
        assert self.state == ReactorState.connecting
        self.__log.info('Connected.')
        self.__keepalive_due_deadline = self.__scheduler.add(self.keepalive_period, self.__keepalive_due_timeout)
        self.__keepalive_abort_deadline = self.__scheduler.add(1.5*self.keepalive_period, self.__keepalive_abort_timeout)

        self.__state = ReactorState.connack

        connect = MqttConnect(self.client_id, self.clean_session, self.keepalive_period)
        self.__queue.insert(0, connect)

        assert not self.__wbuf
        num_bytes_flushed = self.__launch_next_queued_packet()

    def __flush(self):
        """Calls send exactly once; returning the number of bytes written.

        Returns
        -------
        int
            Number of bytes written.
        """

        num_bytes_written = 0
        if self.__wbuf:
            try:
                num_bytes_written = self.socket.send(self.__wbuf)
                self.__wbuf = bytearray(self.__wbuf[num_bytes_written:])
            except socket.error as e:
                if e.errno == errno.EWOULDBLOCK:
                    # No write space ready.
                    pass
                elif e.errno == errno.EPIPE:
                    self.__log.error("Remote unexpectedly closed the connection (errno=%d); Aborting.", e.errno)
                    self.__abort(SocketError(e.errno))
                else:
                    self.__log.error("%s (errno=%d); Aborting.", e.strerror, e.errno)
                    self.__abort(SocketError(e.errno))

        return num_bytes_written

    def __terminate(self):
        if self.state in (ReactorState.connecting,
                          ReactorState.connack,
                          ReactorState.connected,
                          ReactorState.stopping):
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            self.socket.close()

        self.__wbuf = bytearray()
        self.__rbuf = bytearray()

        if self.__keepalive_abort_deadline is not None:
            self.__keepalive_abort_deadline.cancel()
            self.__keepalive_abort_deadline = None

        if self.__keepalive_due_deadline is not None:
            self.__keepalive_due_deadline.cancel()
            self.__keepalive_due_deadline = None

        if self.clean_session:
            self.__queue = []

    def __abort_protocol_violation(self, m, *params):
        self.__log.warning(m, *params)
        self.__abort(ProtocolViolationError(m % params))

    def __abort(self, e):
        self.__terminate()

        self.__state = ReactorState.error
        self.__error = e

    def __keepalive_due_timeout(self):
        self.__assert_state_rules()
        assert self.__keepalive_due_deadline is not None

        assert self.state in (
            ReactorState.connack,
            ReactorState.connected,
            ReactorState.stopping,
        )

        self.__queue_and_flush(MqttPingreq())
        self.__keepalive_due_deadline = None

        self.__assert_state_rules()

    def __keepalive_abort_timeout(self):
        self.__assert_state_rules()

        assert self.__keepalive_due_deadline is None
        assert self.__keepalive_abort_deadline is not None

        assert self.state in (
            ReactorState.connack,
            ReactorState.connected,
            ReactorState.stopping,
        )

        self.__abort(KeepaliveTimeoutReactorError())

        self.__assert_state_rules()

    def write(self):
        self.__assert_state_rules()

        if self.state == ReactorState.init:
            pass
        elif self.state == ReactorState.connecting:
            e = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if e == 0:
                self.__on_connect()
            elif errno.EINPROGRESS:
                pass
            else:
                self.__abort(SocketError(e.errno))
        elif self.state == ReactorState.connack:
            self.__flush()
        elif self.state == ReactorState.closed:
            pass
        elif self.state == ReactorState.error:
            pass
        else:
            raise NotImplementedError()

        self.__assert_state_rules()
