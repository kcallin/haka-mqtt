import socket
import ssl
import unittest

from haka_mqtt.reactor import ReactorError, MutePeerReactorError, ConnectReactorError, SocketReactorError, \
    RecvTimeoutReactorError, AddressReactorError, DecodeReactorError, ProtocolReactorError, SslReactorError
from mqtt_codec.packet import ConnackResult


class TestReactorErrorRepr(unittest.TestCase):
    def test_reactor_error(self):
        repr(ReactorError())

    def test_mute_peer_reactor_error(self):
        repr(MutePeerReactorError())

    def test_connect_reactor_error(self):
        repr(ConnectReactorError(ConnackResult.fail_bad_client_id))

    def test_socket_reactor_error(self):
        repr(SocketReactorError(11))

    def test_address_reactor_error(self):
        repr(AddressReactorError(socket.gaierror(-1, 'hi')))

    def test_decode_reactor_error(self):
        repr(DecodeReactorError('asdfasdfasdf'))

    def test_protocol_reactor_error(self):
        repr(ProtocolReactorError('protocol error text'))

    def test_ssl_reactor_error(self):
        repr(SslReactorError(ssl.SSLError('args', 'args')))


class TestReactorErrorEq(unittest.TestCase):
    def test_recv_timeout_reactor_error(self):
        rtre0 = RecvTimeoutReactorError()
        rtre1 = RecvTimeoutReactorError()
        self.assertEqual(rtre0, rtre1)

    @unittest.skip("SSLError.__eq__ doesn't work.")
    def test_ssl_reactor_error(self):
        sre0 = SslReactorError(ssl.SSLError('args', 'args'))
        sre1 = SslReactorError(ssl.SSLError('args', 'args'))
        self.assertEqual(sre0, sre1)
