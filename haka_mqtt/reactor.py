import errno
import socket
import logging
from binascii import b2a_hex
from io import BytesIO
from itertools import cycle
import os

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
    MqttDisconnect,
    MqttPingreq,
    MqttPingresp,
    MqttPubrec,
    MqttPubrel,
    MqttPubcomp,
    ConnackResult,
    SubscribeResult,
)
from haka_mqtt.on_str import HexOnStr, ReprOnStr


class ReactorProperties(object):
    """
    Attributes
    ----------
    socket_factory: haka_mqtt.socket_factory.SocketFactory
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
        self.socket_factory = None
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
    def __init__(self, topic, ask_max_qos):
        self.__topic = topic
        self.__ask_max_qos = ask_max_qos
        self.__granted_max_qos = None

    @property
    def topic(self):
        return self.__topic

    @property
    def ask_max_qos(self):
        return self.__ask_max_qos

    @property
    def granted_max_qos(self):
        return self.__granted_max_qos

    def _set_granted_max_qos(self, qos):
        self.__granted_max_qos = qos


class ReactorError(object):
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

    def __repr__(self):
        return '{}()'.format(self.__class__.__name__)


class SocketError(ReactorError):
    """
    Attributes
    ----------
    errno: int
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
        return 'SocketError(<{}: {}>)'.format(errno.errorcode[self.errno], self.errno)

    def __eq__(self, other):
        return self.errno == other.errno


class AddressingReactorError(ReactorError):
    def __init__(self, gaierror):
        """
        Parameters
        ----------
        gaierror: socket.gaierror
        """
        assert isinstance(gaierror, socket.gaierror)
        self.__errno = gaierror.errno
        self.__desc = gaierror.strerror

    @property
    def errno(self):
        """

        Returns
        -------
        int
        """
        return self.__errno

    @property
    def description(self):
        """

        Returns
        -------
        str
        """
        return self.__desc

    def __repr__(self):
        return '{}({} ({}))'.format(self.__class__.__name__, self.errno, self.description)


class DecodeReactorError(ReactorError):
    def __init__(self, description):
        self.description = description


class ProtocolViolationError(ReactorError):
    def __init__(self, description):
        self.description = description


FREE_LAUNCH_PACKET_TYPES = {
    MqttControlPacketType.connect,
    MqttControlPacketType.connack,
    MqttControlPacketType.puback,
    MqttControlPacketType.pubrec,
    MqttControlPacketType.pubrel,
    MqttControlPacketType.pubcomp,
    MqttControlPacketType.subscribe,
    MqttControlPacketType.suback,
    MqttControlPacketType.unsubscribe,
    MqttControlPacketType.unsuback,
    MqttControlPacketType.pingreq,
    MqttControlPacketType.pingresp,
    MqttControlPacketType.disconnect,
}


class QueuedPacket(object):
    def __init__(self, packet):
        self.__in_flight = False
        self.__packet = packet

    def in_flight(self):
        """True if packet is in-flight; False otherwise."""
        return self.__in_flight

    @property
    def packet(self):
        return self.__packet

    def __repr__(self):
        return 'QueuedPacket({})'.format(repr(self.packet))

class Reactor:
    def __init__(self, properties):
        """

        Parameters
        ----------
        properties: ReactorProperties
        """

        assert properties.client_id is not None
        assert properties.socket_factory is not None
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

        self.__socket_factory = properties.socket_factory
        self.socket = None
        self.endpoint = properties.endpoint
        self.__state = ReactorState.init
        self.__error = None

        self.__in_flight_packet_ids = set()
        self.__packet_id_iter = cycle(xrange(0, 2**16-1))

        self.__preflight_queue = []

        # Publish packets must be ack'd in order of publishing
        # [MQTT-4.6.0-2], [MQTT-4.6.0-3]
        self.__in_flight_publish = []

        # No specific requirement exists for subscribe suback ordering.
        self.__in_flight_subscribe = {}

        # It MUST send PUBREL packets in the order in which the corresponding PUBREC packets were
        # received (QoS 2 messages) [MQTT-4.6.0-4]
        self.__in_flight_pubrel = []

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

        Returns
        --------
        QueuedPacket
        """
        assert self.state == ReactorState.connected
        p = MqttSubscribe(self.__packet_id_iter.next(), topics)
        self.__queue_and_flush(p)

        return p

    def unsubscribe(self, topics):
        pass

    def publish(self, topic, payload, qos, retain=False):
        """
        Parameters
        -----------
        topic: str
        payload: bytes
        qos: int
            0 <= qos <= 2
        retain: False

        Return
        -------
        QueuedPacket
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
        # TODO: Does this fulfill MQTT ordering requirements?
        in_flight_packets = self.__in_flight_publish + self.__in_flight_pubrel

        self.__in_flight_publish = []
        self.__in_flight_pubrel = []
        self.__in_flight_subscribe = {}
        self.__in_flight_connect = []

        preflight_keep_packet_types = (
            MqttControlPacketType.publish,
            MqttControlPacketType.pubrel,
        )
        self.__preflight_queue = ([QueuedPacket(ifp) for ifp in in_flight_packets]
                                 + [qp for qp in self.__preflight_queue if qp.packet.packet_type in preflight_keep_packet_types])
        self.__wbuf = bytearray()
        self.__rbuf = bytearray()
        self.socket = self.__socket_factory()

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
                self.__abort_socket_error(SocketError(e.errno))

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
            if not self.__in_flight_subscribe:
                self.__queue_and_flush(MqttDisconnect())

                if not self.__wbuf:
                    self.__log.info('Shutting down outgoing stream.')
                    self.socket.shutdown(socket.SHUT_WR)

                # Stop keepalive messages.
                # TODO: What if remote socket takes forever to close?

            self.__state = ReactorState.stopping
        else:
            raise NotImplementedError(self.state)

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
        self.__keepalive_abort_deadline = self.__scheduler.add(1.5*self.keepalive_period,
                                                               self.__keepalive_abort_timeout)

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
                elif header.packet_type == MqttControlPacketType.pubcomp:
                    self.__on_pubcomp(self.__decode_packet_body(header, num_header_bytes, MqttPubcomp))
                elif header.packet_type == MqttControlPacketType.pubrec:
                    self.__on_pubrec(self.__decode_packet_body(header, num_header_bytes, MqttPubrec))
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
        if self.state not in INACTIVE_STATES:
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
                    self.__abort_socket_error(SocketError(e.errno))

        self.__assert_state_rules()
        return num_bytes_read

    def __on_connack_accepted(self, connack):
        if connack.session_present and self.clean_session:
            # [MQTT-3.2.2-1]
            self.__abort_protocol_violation('Server indicates a session is present when none was requested.')
        else:
            if self.on_connack is not None:
                self.on_connack(self, connack)

            self.__launch_next_queued_packet()

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
            self.__abort_protocol_violation('Received connack at an inappropriate time.')

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
            raise NotImplementedError(self.state)

    def __on_suback(self, suback):
        """

        Parameters
        ----------
        suback: MqttSuback

        """
        if self.state is ReactorState.connected:
            subscribe = self.__in_flight_subscribe.pop(suback.packet_id, None)
            if subscribe:
                if len(suback.results) == len(subscribe.topics):
                    self.__log.info('Received %s.', repr(suback))
                    if self.on_suback is not None:
                        self.on_suback(self, suback)
                else:
                    m = 'Received %s as a response to %s, but the number of subscription' \
                        ' results does not equal the number of subscription requests; aborting.'
                    self.__abort_protocol_violation(m,
                                                    repr(suback),
                                                    repr(subscribe))
            else:
                self.__abort_protocol_violation('Received %s for a mid that is not in-flight; aborting.',
                                                repr(suback))
        else:
            raise NotImplementedError(self.state)

    def __on_puback(self, puback):
        """

        Parameters
        ----------
        puback: MqttPuback

        """
        if self.state is ReactorState.connected:
            try:
                publish = self.__in_flight_publish[0]
            except IndexError:
                publish = None

            if publish and publish.packet_id == puback.packet_id:
                if publish.qos == 1:
                    del self.__in_flight_publish[0]
                    self.__log.info('Received %s.', repr(puback))

                    if self.on_puback is not None:
                        self.on_puback(self, puback)
                else:
                    self.__abort_protocol_violation('Received %s, an inappropriate response to qos=%d %s; aborting.',
                                                    ReprOnStr(puback),
                                                    publish.qos,
                                                    ReprOnStr(publish))
            elif publish and puback.packet_id in [p.packet_id for p in self.__in_flight_publish]:
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
            try:
                publish = self.__in_flight_publish[0]
            except IndexError:
                publish = None

            if publish and publish.packet_id == pubrec.packet_id:
                if publish.qos == 2:
                    del self.__in_flight_publish[0]
                    self.__log.info('Received %s.', repr(pubrec))

                    if self.on_pubrec is not None:
                        self.on_pubrec(self, pubrec)

                    self.__queue_before_next_publish(MqttPubrel(pubrec.packet_id))
                else:
                    self.__abort_protocol_violation('Received %s in response to qos=%d publish %s; aborting.',
                                                    ReprOnStr(pubrec),
                                                    publish.qos,
                                                    ReprOnStr(publish))
            elif publish and pubrec.packet_id in [p.packet_id for p in self.__in_flight_publish]:
                m = 'Received %s when packet_id=%d was next-in-flight; aborting.'
                self.__abort_protocol_violation(m,
                                                ReprOnStr(pubrec),
                                                publish.packet_id)
            else:
                m = 'Received %s when packet_id=%d was not in-flight; aborting.'
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
            try:
                pubrel = self.__in_flight_pubrel[0]
            except IndexError:
                pubrel = None

            if pubrel and pubrel.packet_id == pubcomp.packet_id:
                del self.__in_flight_pubrel[0]
                self.__log.info('Received %s.', repr(pubcomp))

                if self.on_pubcomp is not None:
                    self.on_pubcomp(self, pubcomp)
            elif pubrel and pubcomp.packet_id in [p.packet_id for p in self.__in_flight_pubrel]:
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
            self.__queue_and_flush(MqttPubcomp(pubrel.packet_id))
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
            self.__abort(DecodeReactorError('Remote closed unexpectedly.'))
        elif self.state in (ReactorState.stopping,):
            if len(self.__rbuf) > 0:
                m = 'While stopping remote closed stream in the middle' \
                    ' of a packet transmission with 0x%s still in the buffer.'
                self.__log.warning(m, b2a_hex(self.__rbuf))
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
            raise NotImplementedError(self.state)

    def __launch_preflight_connect_packet(self):
        """Takes messages from the preflight_queue and places them in
        the in_flight_queues.

        Takes messages from the in_flight_queues in the order they
        appear in the preflight_queues.

        Returns
        -------
        int
            Returns number of bytes flushed to output buffers.
        """

        num_bytes_flushed = 0
        assert not self.__wbuf

        packet = self.__preflight_queue.pop(0).packet
        assert packet.packet_type is MqttControlPacketType.connect

        bio = BytesIO()
        packet.encode(bio)
        self.__log.info('Launching message %s.', repr(packet))
        self.__wbuf.extend(bio.getvalue())

        # Write as many bytes as possible.
        num_bytes_flushed = self.__flush()
        self.__in_flight_connect.append(packet)

        self.__log.debug('Wrote %d bytes 0x%s.', num_bytes_flushed, HexOnStr(self.__wbuf[0:num_bytes_flushed]))
        self.__wbuf = self.__wbuf[num_bytes_flushed:]

        return num_bytes_flushed

    def __launch_preflight_packets(self):
        """Takes messages from the preflight_queue and places them in
        the in_flight_queues.

        Takes messages from the in_flight_queues in the order they
        appear in the preflight_queues.

        Returns
        -------
        int
            Returns number of bytes flushed to output buffers.
        """

        num_bytes_flushed = 0
        num_publish_in_flight = len(self.__in_flight_publish)
        launch_indexes = []

        # Select launch order.
        for preflight_idx, queued_packet in enumerate(self.__preflight_queue):
            packet = queued_packet.packet

            if packet.packet_type is MqttControlPacketType.publish:
                if num_publish_in_flight < self.max_inflight_publish:
                    launch_indexes.append(preflight_idx)
                    num_publish_in_flight += 1
            elif packet.packet_type in FREE_LAUNCH_PACKET_TYPES:
                launch_indexes.append(preflight_idx)
            else:
                raise NotImplementedError(packet.packet_type)

        # Prepare bytes for launch
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
        for launch_idx in launch_indexes:
            packet = self.__preflight_queue[launch_idx].packet

            num_bytes_encoded = packet.encode(bio)
            if wbuf_size + num_bytes_encoded <= max_buf_size:
                wbuf_size += num_bytes_encoded
                packet_end_offsets.append(wbuf_size)
            else:
                break

        # Write as many bytes as possible.
        self.__wbuf.extend(bio.getvalue())
        num_bytes_flushed = self.__flush()

        # Mark launched messages as in-flight.
        num_messages_launched = 0
        for packet_end_offset in packet_end_offsets:
            if num_bytes_flushed > packet_end_offset:
                num_messages_launched += 1
            else:
                break

        launch_indexes = launch_indexes[0:num_messages_launched]
        launch_indexes.reverse()
        launched_packets = []
        for launch_index in launch_indexes:
            launched_packets.insert(0, self.__preflight_queue.pop(launch_index).packet)

        for packet in launched_packets:
            self.__log.info('Launching message %s.', repr(packet))

            # if packet.packet_type is MqttControlPacketType.connect:
            #     pass
            # elif packet.packet_type is MqttControlPacketType.connack:
            #     pass
            if packet.packet_type is MqttControlPacketType.publish:
                self.__in_flight_publish.append(packet)
            elif packet.packet_type is MqttControlPacketType.puback:
                pass
            # elif packet.packet_type is MqttControlPacketType.pubrec:
            #     pass
            elif packet.packet_type is MqttControlPacketType.pubrel:
                self.__in_flight_pubrel.append(packet)
            # elif packet.packet_type is MqttControlPacketType.pubcomp:
            #     pass
            elif packet.packet_type is MqttControlPacketType.subscribe:
                self.__in_flight_subscribe[packet.packet_id] = packet
            # elif packet.packet_type is MqttControlPacketType.suback:
            #     pass
            elif packet.packet_type is MqttControlPacketType.unsubscribe:
                pass
            # elif packet.packet_type is MqttControlPacketType.unsuback:
            #     pass
            # elif packet.packet_type is MqttControlPacketType.pingreq:
            #     pass
            # elif packet.packet_type is MqttControlPacketType.pingresp:
            #     pass
            # elif packet.packet_type is MqttControlPacketType.disconnect:
            #     pass

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

        num_bytes_flushed = 0
        if self.state is ReactorState.connack:
            if self.__in_flight_connect:
                num_bytes_flushed = self.__launch_preflight_packets()
            else:
                num_bytes_flushed = self.__launch_preflight_connect_packet()

        else:
            num_bytes_flushed = self.__launch_preflight_packets()

        return num_bytes_flushed

    def __queue_before_next_publish(self, preflight_packet):
        """

        Parameters
        ----------
        preflight_packet

        Returns
        -------
        int
            Returns number of bytes flushed to underlying socket.
        """

        insert_idx = len(self.__preflight_queue)
        for packet_idx, queued_packet in enumerate(self.__preflight_queue):
            if queued_packet.packet.packet_type is MqttControlPacketType.publish:
                insert_idx = packet_idx
                break

        self.__preflight_queue.insert(insert_idx, QueuedPacket(preflight_packet))

        return self.__launch_next_queued_packet()
        # if num_bytes_flushed == 0:
        #     self.__log.info('Queuing %s for delivery.', repr(preflight_packet))
        #
        # return num_bytes_flushed

    def __queue_and_flush(self, preflight_packet):
        """

        Parameters
        ----------
        preflight_packet

        Returns
        -------
        int
            Returns number of bytes flushed to underlying socket.
        """
        self.__preflight_queue.append(QueuedPacket(preflight_packet))

        num_bytes_flushed = self.__launch_next_queued_packet()
        if num_bytes_flushed == 0:
            self.__log.info('Queuing %s for delivery.', repr(preflight_packet))

        return num_bytes_flushed

    def __on_connect(self):
        assert self.state == ReactorState.connecting
        self.__log.info('Connected.')
        self.__keepalive_due_deadline = self.__scheduler.add(self.keepalive_period, self.__keepalive_due_timeout)
        self.__keepalive_abort_deadline = self.__scheduler.add(1.5*self.keepalive_period,
                                                               self.__keepalive_abort_timeout)

        self.__state = ReactorState.connack

        connect = MqttConnect(self.client_id, self.clean_session, self.keepalive_period)
        self.__preflight_queue.insert(0, QueuedPacket(connect))

        assert not self.__wbuf
        self.__launch_next_queued_packet()

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
            except socket.error as e:
                if e.errno == errno.EWOULDBLOCK:
                    # No write space ready.
                    pass
                elif e.errno == errno.EPIPE:
                    self.__log.error("Remote unexpectedly closed the connection (<%s: %d>); Aborting.",
                                     errno.errorcode[e.errno],
                                     e.errno)
                    self.__abort(SocketError(e.errno))
                else:
                    self.__abort_socket_error(SocketError(e.errno))

        return num_bytes_written

    def __terminate(self):
        if self.state in (ReactorState.connecting,
                          ReactorState.connack,
                          ReactorState.connected,
                          ReactorState.stopping):
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()

        self.__wbuf = bytearray()
        self.__rbuf = bytearray()

        if self.__keepalive_abort_deadline is not None:
            self.__keepalive_abort_deadline.cancel()
            self.__keepalive_abort_deadline = None

        if self.__keepalive_due_deadline is not None:
            self.__keepalive_due_deadline.cancel()
            self.__keepalive_due_deadline = None

    def __abort_socket_error(self, se):
        """

        Parameters
        ----------
        se: SocketError
        """
        self.__log.error('%s (<%s: %d>).  Aborting.',
                         os.strerror(se.errno),
                         errno.errorcode[se.errno],
                         se.errno)
        self.__abort(se)

    def __abort_protocol_violation(self, m, *params):
        self.__log.error(m, *params)
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

        if self.state not in INACTIVE_STATES:
            if self.state == ReactorState.connecting:
                e = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if e == 0:
                    self.__on_connect()
                elif errno.EINPROGRESS:
                    pass
                else:
                    self.__abort_socket_error(SocketError(e.errno))
            elif self.state in (ReactorState.connack, ReactorState.connected, ReactorState.stopping):
                self.__launch_next_queued_packet()
            else:
                raise NotImplementedError(self.state)

        self.__assert_state_rules()
