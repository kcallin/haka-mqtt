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

from haka_mqtt.mqtt import MqttConnect, MqttSubscribe, MqttFixedHeader, MqttControlPacketType, MqttConnack, MqttSuback


class ReactorProperties:
    """
    Attributes
    ----------
    socket: socket.socket
    client_id: str
    """
    socket = None
    endpoint = None
    client_id = None


@unique
class ReactorState(IntEnum):
    init = 0
    connecting = 1
    connack = 2
    connected = 3
    error = 4
    closed = 5


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


class Reactor:
    def __init__(self, properties):
        """

        Parameters
        ----------
        properties: ReactorProperties
        """

        assert properties.socket is not None
        assert properties.endpoint is not None

        self.__log = logging.getLogger('mqtt_reactor')
        self.__wbuf = []
        self.__rbuf = []

        self.socket = properties.socket
        self.endpoint = properties.endpoint
        self.__packet_id_iter = cycle(xrange(0, 2**16-1))
        self.__queue = []
        self.__state = ReactorState.init
        self.__error = None

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
        return self.__state

    def subscribe(self, topics):
        """

        Parameters
        ----------
        topics: iterable of MqttTopic

        Returns
        -------

        """
        assert self.state == ReactorState.connected
        subscribe = MqttSubscribe(self.__packet_id_iter.next(), topics)
        self.__write_packet(subscribe)

    def start(self):
        assert self.state == ReactorState.init
        self.__log.info('Starting.')

        try:
            self.socket.connect(self.endpoint)
        except socket.error as e:
            if e.errno == errno.EINPROGRESS:
                # Connection in progress.
                self.__log.info('Connecting')
                self.__state = ReactorState.connecting
            else:
                self.__state = ReactorState.error
                self.__error = SocketError(e)

    def stop(self):
        pass

    def terminate(self):
        if self.state == ReactorState.init:
            pass
        elif self.state == ReactorState.connecting:
            self.socket.close()
            self.__state == ReactorState.closed
        elif self.state == ReactorState.closed:
            pass
        elif self.state == ReactorState.error:
            pass
        else:
            raise NotImplementedError()

    def want_read(self):
        return self.state in [ReactorState.connack]

    def want_write(self):
        return bool(self.__wbuf) or self.state == ReactorState.connecting

    def read(self):
        buf = bytearray(1024)
        num_bytes_received = self.socket.recv_into(buf)
        self.__log.debug('Received %d bytes 0x%s', num_bytes_received, b2a_hex(buf[0:num_bytes_received]))

        num_bytes_consumed, header = MqttFixedHeader.decode(buf)
        if len(buf) >= header.remaining_len:
            body = buf[num_bytes_consumed:]
            if header.packet_type == MqttControlPacketType.connack:
                num_bytes_consumed, connack = MqttConnack.decode_body(header, body)
                self.__on_connack(connack)
            elif header.packet_type == MqttControlPacketType.suback:
                num_bytes_consumed, suback = MqttSuback.decode_body(header, body)
                self.__on_suback(suback)
            else:
                assert False

    def __on_connack(self, connack):
        if self.state is ReactorState.connack:
            self.__log.info('Received %s.', repr(connack))
            self.__state = ReactorState.connected
        else:
            assert False

    def __on_suback(self, suback):
        if self.state is ReactorState.connected:
            self.__log.info('Received %s.', repr(suback))
        else:
            assert False

    def __write_packet(self, packet):
        self.__log.info('Sending %s.', repr(packet))
        bio = BytesIO()
        packet.encode(bio)
        buf = bio.getvalue()
        self.__log.debug('Sending %d bytes 0x%s.', len(buf), b2a_hex(buf))
        self.__wbuf.append(buf)
        self.__flush()

    def __on_connect(self):
        assert self.state == ReactorState.connecting
        self.__state = ReactorState.connack
        self.__write_packet(MqttConnect('hello', True, 10*60))

    def __flush(self):
        while self.__wbuf:
            try:
                num_bytes_written = self.socket.send(self.__wbuf[0])
                assert len(self.__wbuf[0]) == num_bytes_written, len(self.__wbuf[0])
                self.__wbuf.pop(0)
            except socket.error as e:
                if e.errno == errno.EWOULDBLOCK:
                    # No write space ready.
                    pass
                else:
                    self.__state = ReactorState.error
                    self.__error = SocketError(e)

    def write(self):
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
