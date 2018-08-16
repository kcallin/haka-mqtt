import errno
import socket
import logging
from binascii import b2a_hex
from io import BytesIO
from itertools import cycle
from time import time

from enum import (
    IntEnum,
    unique,
)

from haka_mqtt.mqtt import MqttConnect, MqttSubscribe, MqttFixedHeader, MqttControlPacketType, MqttConnack, MqttSuback, \
    UnderflowDecodeError, DecodeError, MqttPublish, MqttPuback
from haka_mqtt.scheduler import Scheduler


class BufferStr(object):
    def __init__(self, buf):
        self.__buf = buf

    def __str__(self):
        return b2a_hex(self.__buf)


class SystemClock():
    def time(self):
        return time()


class SettableClock():
    def __init__(self):
        self.__time = 0

    def set_time(self, t):
        self.__time = t

    def time(self):
        return self.__time


class ReactorProperties:
    """
    Attributes
    ----------
    socket: socket.socket
    client_id: str
    clock:
    """
    socket = None
    endpoint = None
    client_id = None
    clock = SystemClock()


@unique
class ReactorState(IntEnum):
    init = 0
    connecting = 1
    connack = 2
    connected = 3
    stopping = 4
    stopped = 5
    error = 6


INACTIVE_STATES = (ReactorState.init, ReactorState.stopped, ReactorState.error)


class ReactorError:
    pass


class SocketError(ReactorError):
    """
    Attributes
    ----------
    error: errno
    """
    def __init__(self, errno):
        """
        Parameters
        ----------
        errno: int
        """
        self.errno = errno


class DecodeReactorError(ReactorError):
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

        self.__log = logging.getLogger('mqtt_reactor')
        self.__wbuf = bytearray()
        self.__rbuf = bytearray()

        self.__client_id = properties.client_id
        self.__clock = properties.clock
        self.__keepalive_period = 10*60
        self.__keepalive_deadline = None
        self.__keepalive_timeout_deadline = None
        self.__last_poll_instant = None

        self.socket = properties.socket
        self.endpoint = properties.endpoint
        self.__packet_id_iter = cycle(xrange(0, 2**16-1))
        self.__queue = []
        self.__state = ReactorState.init
        self.__error = None
        self.__in_flight_packets = {}

        self.__scheduler = Scheduler()

        self.on_puback = None
        self.on_suback = None
        self.on_connack = None
        self.on_publish = None

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
            assert self.__keepalive_deadline is None
            assert self.__keepalive_timeout_deadline is None
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
        self.__write_packet(subscribe)

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
        """
        self.__assert_state_rules()
        assert self.state is ReactorState.connected

        p = MqttPublish(next(self.__packet_id_iter), topic, payload, False, qos, retain)
        self.__in_flight_packets[p.packet_id] = p
        self.__write_packet(p)

        self.__assert_state_rules()

    def start(self):
        self.__assert_state_rules()
        assert self.state == ReactorState.init

        self.__log.info('Starting.')

        try:
            self.__state = ReactorState.connecting
            self.socket.connect(self.endpoint)
            self.__on_connect()
        except socket.error as e:
            if e.errno == errno.EINPROGRESS:
                # Connection in progress.
                self.__log.info('Connecting.')
            else:
                self.__abort(ReactorState(e))

        self.__assert_state_rules()

    def stop(self):
        self.__assert_state_rules()
        self.__assert_state_rules()

    def terminate(self):
        self.__assert_state_rules()

        if self.state not in INACTIVE_STATES:
            self.__terminate()

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
        self.__log.debug('Received %d bytes 0x%s', len(new_bytes), BufferStr(new_bytes))
        self.__rbuf.extend(new_bytes)

        num_header_bytes, header = MqttFixedHeader.decode(self.__rbuf)
        num_packet_bytes = num_header_bytes + header.remaining_len
        if len(self.__rbuf) >= num_packet_bytes:
            if header.packet_type == MqttControlPacketType.connack:
                self.__on_connack(self.__decode_packet_body(header, num_header_bytes, MqttConnack))
            elif header.packet_type == MqttControlPacketType.suback:
                self.__on_suback(self.__decode_packet_body(header, num_header_bytes, MqttSuback))
            elif header.packet_type == MqttControlPacketType.puback:
                self.__on_suback(self.__decode_packet_body(header, num_header_bytes, MqttPuback))
            elif header.packet_type == MqttControlPacketType.publish:
                self.__on_publish(self.__decode_packet_body(header, num_header_bytes, MqttPublish))
            else:
                self.__abort(DecodeReactorError('Received unsupported message type {}.'.format(header.packet_type)))

    def read(self):
        self.__assert_state_rules()

        try:
            new_bytes = self.socket.recv(4096)
            if new_bytes:
                self.__on_recv_bytes(new_bytes)
            else:
                self.__on_muted_remote()

        except UnderflowDecodeError:
            # Not enough header bytes.
            pass
        except DecodeError as e:
            self.__abort(DecodeReactorError(str(e)))
        except socket.error as e:
            if e.errno == errno.EWOULDBLOCK:
                # No write space ready.
                pass
            else:
                self.__abort(SocketError(e))

        self.__assert_state_rules()

    def __on_connack(self, connack):
        if self.state is ReactorState.connack:
            self.__log.info('Received %s.', repr(connack))
            self.__state = ReactorState.connected

            if self.on_connack is not None:
                self.on_connack(self, connack)
        else:
            self.__abort(DecodeReactorError('Received connack at an inappropriate time.'))

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
                self.__write_packet(MqttPuback(publish.packet_id))
            elif publish.qos == 2:
                raise NotImplementedError()
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
                self.__in_flight_packets.pop(puback.packet_id)
                in_flight = True
            except KeyError:
                in_flight = False

            if in_flight:
                self.__log.info('Received %s.', repr(puback))
                if self.on_suback is not None:
                    self.on_suback(self, puback)
            else:
                self.__log.warning('Received %s for a mid that is not in-flight; aborting.', repr(puback))
                self.__abort(DecodeReactorError())
        else:
            assert False, 'Received MqttPuback at an inappropriate time.'

    def __on_muted_remote(self):
        if self.state in (ReactorState.connack, ReactorState.connected):
            self.__log.warning('Remote closed stream unexpectedly.')
            self.__abort(DecodeReactorError('Remote closed unexpectedly.'))
        elif self.state in (ReactorState.stopping,):
            raise NotImplementedError()
        else:
            assert False, 'Received muted_remote at an inappropriate time.'

    def __write_packet(self, packet):
        self.__log.info('Sending %s.', repr(packet))
        bio = BytesIO()
        packet.encode(bio)
        buf = bio.getvalue()
        self.__log.debug('Sending %d bytes 0x%s.', len(buf), BufferStr(buf))
        self.__wbuf.extend(buf)
        self.__flush()

    def __on_connect(self):
        assert self.state == ReactorState.connecting
        self.__state = ReactorState.connack
        self.__write_packet(MqttConnect(self.client_id, True, self.keepalive_period))

    def __flush(self):
        while self.__wbuf:
            try:
                num_bytes_written = self.socket.send(self.__wbuf)
                self.__wbuf = bytearray(self.__wbuf[num_bytes_written:])
            except socket.error as e:
                if e.errno == errno.EWOULDBLOCK:
                    # No write space ready.
                    pass
                else:
                    self.__abort(SocketError(e))

    def __terminate(self):
        if self.state in (ReactorState.connecting,
                          ReactorState.connack,
                          ReactorState.connected,
                          ReactorState.stopping):
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()

        if self.__keepalive_timeout_deadline is not None:
            self.__keepalive_timeout_deadline.cancel()
            self.__keepalive_timeout_deadline = None

        if self.__keepalive_deadline is not None:
            self.__keepalive_deadline.cancel()
            self.__keepalive_deadline = None

    def __abort(self, e):
        self.__terminate()

        self.__state = ReactorState.error
        self.__error = e

    def __keepalive_due(self):
        pass

    def __keepalive_timeout(self):
        pass

    def remaining(self):
        return self.__scheduler.remaining()

    def poll(self):
        self.__assert_state_rules()

        now = self.__clock.time()
        if self.last_poll_instant is None:
            duration_since_last_poll = 0
        else:
            duration_since_last_poll = now - self.last_poll_instant
        self.__last_poll_instant = now

        self.__scheduler.poll(duration_since_last_poll)
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
                self.__log.info('Connecting.')
            else:
                self.__state = ReactorState.error
                self.__error = SocketError(e)
        elif self.state == ReactorState.connack:
            self.__flush()
        elif self.state == ReactorState.closed:
            pass
        elif self.state == ReactorState.error:
            pass
        else:
            raise NotImplementedError()

        self.__assert_state_rules()
