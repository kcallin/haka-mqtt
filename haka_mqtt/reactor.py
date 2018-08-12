import errno
import socket
import logging
from binascii import b2a_hex
from io import BytesIO

from enum import (
    IntEnum,
    unique,
)

from haka_mqtt.mqtt import MqttConnect


class ReactorProperties:
    """
    Attributes
    ----------
    socket: socket.socket
    """
    socket = None
    endpoint = None


@unique
class ReactorState(IntEnum):
    init = 0
    connecting = 1
    connack = 4
    error = 2
    closed = 3


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

    def __on_connect(self):
        assert self.state == ReactorState.connecting

        self.__log.info('Connected.')
        self.__state = ReactorState.connack
        connect_packet = MqttConnect('hello', True, 10*60)
        bio = BytesIO()
        connect_packet.encode(bio)
        self.__wbuf.append(bio.getvalue())
        self.__flush()

    def __flush(self):
        while self.__wbuf:
            try:
                num_bytes_written = self.socket.send(self.__wbuf[0])
                assert len(self.__wbuf[0]) == num_bytes_written
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
