"""Testing for the reactor.py.


CHECKED-KC0: tests that are at a production level of readiness.

"""
from __future__ import print_function

import errno
import logging
import os
import ssl
import sys
import unittest
import socket
from io import BytesIO

from mock import Mock

from mqtt_codec.packet import (
    MqttConnect,
    ConnackResult,
    MqttConnack,
    MqttTopic,
    MqttSubscribe,
    SubscribeResult,
    MqttSuback,
    MqttPublish,
    MqttPuback,
    MqttPubrec,
    MqttPubrel,
    MqttPubcomp,
    MqttPingreq,
    MqttDisconnect, MqttWill, MqttUnsubscribe, MqttUnsuback, MqttPingresp)
from haka_mqtt.mqtt_request import MqttPublishTicket, MqttPublishStatus, MqttSubscribeStatus, MqttSubscribeTicket, \
    MqttUnsubscribeTicket
from haka_mqtt.reactor import (
    Reactor,
    ReactorProperties,
    ReactorState,
    KeepaliveTimeoutReactorError,
    ConnectReactorError, INACTIVE_STATES, SocketReactorError, AddressReactorError, DecodeReactorError,
    ProtocolReactorError, INACTIVE_SOCK_STATES, SocketState, MqttState)
from haka_mqtt.scheduler import Scheduler


def buffer_packet(packet):
    """Creates a str for packet.encode and returns it.

    Parameters
    ----------
    packet: MqttPacketBody

    Returns
    -------
    str
    """
    bio = BytesIO()
    packet.encode(bio)
    return bio.getvalue()


def socket_error(errno):
    return socket.error(errno, os.strerror(errno))


class DebugFuture(object):
    def __init__(self):
        self.__cancelled = False
        self.__done = False
        self.__callbacks = []

        self.__result = None
        self.__exception = None

    def __notify(self):
        for cb in self.__callbacks:
            cb(self)

    def cancel(self):
        if self.done():
            rv = False
        else:
            self.__cancelled = True
            self.__done = True
            self.__notify()
            rv = True

        return rv

    def set_result(self, result):
        """
        Sets the result of the work associated with the Future to result.

        This method should only be used by Executor implementations and unit tests.
        """
        self.__result = result

    def set_exception(self, exception):
        """
            Sets the result of the work associated with the Future to the Exception exception.

            This method should only be used by Executor implementations and unit tests.
        """
        self.__exception = exception

    def set_done(self, done):
        self.__done = done
        if done:
            self.__notify()

    def cancelled(self):
        return self.__cancelled

    def done(self):
        return self.__done

    def result(self, timeout=None):
        return self.__result

    def exception(self, timeout=None):
        return self.__exception

    def add_done_callback(self, fn):
        if self.done():
            fn(self)
        else:
            self.__callbacks.append(fn)


class TestReactor(unittest.TestCase):
    def reactor_properties(self):
        p = ReactorProperties()
        p.socket_factory = lambda: self.socket
        p.endpoint = self.endpoint
        p.client_id = self.client_id
        p.keepalive_period = self.keepalive_period
        p.scheduler = self.scheduler
        p.clean_session = True
        p.name_resolver = self.name_resolver

        return p

    def setup_logging(self):
        log_env_var = 'LOGGING'
        formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s  %(message)s')
        if log_env_var in os.environ:
            self.handler = logging.StreamHandler(sys.stdout)
        else:
            self.handler = logging.NullHandler()
        self.handler.setFormatter(formatter)

        self.log = logging.getLogger(self.__class__.__name__)
        self.logs = [
            logging.getLogger('haka'),
            self.log
        ]
        for log in self.logs:
            log.setLevel(logging.DEBUG)
            log.addHandler(self.handler)

    def teardown_logging(self):
        for log in self.logs:
            log.removeHandler(self.handler)

    def af_inet_name_resolution(self):
        """
        ********************
        family AF_INET
        socktype 1
        proto 6
        canonname
        sockaddr ('93.184.216.34', 80)

        ********************
        family AF_INET6
        socktype 1
        proto 6
        canonname
        sockaddr ('2606:2800:220:1:248:1893:25c8:1946', 80, 0, 0)
        """
        return socket.AF_INET, 1, 6, '', ('93.184.216.34', 80)

    def af_inet6_name_resolution(self):
        return socket.AF_INET6, 1, 6, '', ('2606:2800:220:1:248:1893:25c8:1946', 80, 0, 0)

    def setUp(self):
        unittest.TestCase.setUp(self)
        self.setup_logging()

        self.socket = Mock()
        self.endpoint = ('test.mosquitto.org', 1883)
        self.name_resolver_future = DebugFuture()
        self.name_resolver_future.set_result([
            self.af_inet_name_resolution(),
            self.af_inet6_name_resolution()
        ])
        self.name_resolver_future.set_done(True)
        self.name_resolver = Mock()
        self.name_resolver.return_value = self.name_resolver_future
        self.expected_sockaddr = self.af_inet_name_resolution()[4]
        self.client_id = 'client'
        self.keepalive_period = 10*60
        self.scheduler = Scheduler()

        self.on_connect_fail = Mock()
        self.on_disconnect = Mock()
        self.on_publish = Mock()
        self.on_pubrel = Mock()
        self.on_pubrec = Mock()
        self.on_pubcomp = Mock()
        self.on_connack = Mock()
        self.on_puback = Mock()
        self.on_suback = Mock()
        self.on_unsuback = Mock()

        self.properties = self.reactor_properties()
        self.reactor = Reactor(self.properties)
        self.reactor.on_publish = self.on_publish
        self.reactor.on_connack = self.on_connack
        self.reactor.on_pubrel = self.on_pubrel
        self.reactor.on_pubcomp = self.on_pubcomp
        self.reactor.on_pubrec = self.on_pubrec
        self.reactor.on_puback = self.on_puback
        self.reactor.on_suback = self.on_suback
        self.reactor.on_unsuback = self.on_unsuback
        self.reactor.on_connect_fail = self.on_connect_fail
        self.reactor.on_disconnect = self.on_disconnect

        self.log.info('%s setUp()', self._testMethodName)

    def tearDown(self):
        try:
            self.log.info('%s tearDown()', self._testMethodName)
            self.assertEqual(0, len(self.scheduler))
            self.assertTrue(self.reactor.state in INACTIVE_STATES)
            self.assertFalse(self.reactor.want_read())
            self.assertFalse(self.reactor.want_write())
        finally:
            self.teardown_logging()

    def set_recv_side_effect(self, rv_iterable):
        self.socket.recv.side_effect = rv_iterable

    def recv_packet_then_ewouldblock(self, p):
        self.set_recv_side_effect([buffer_packet(p), socket.error(errno.EWOULDBLOCK)])
        self.reactor.read()
        self.socket.recv.assert_called_once()
        self.socket.recv.reset_mock()
        self.socket.recv.side_effect = None
        self.socket.recv.return_value = None

    def recv_eof(self):
        self.set_recv_side_effect([''])
        self.reactor.read()
        self.socket.recv.assert_called_once()
        self.socket.recv.reset_mock()
        self.socket.recv.side_effect = None
        self.socket.recv.return_value = None

    def set_send_side_effect(self, rv_iterable):
        self.socket.send.side_effect = rv_iterable

    def set_send_packet_side_effect(self, p):
        try:
            packet_it = iter(p)
        except TypeError:
            packet_it = [p]

        self.set_send_side_effect([sum(len(buffer_packet(p)) for p in packet_it)])

    def send_packet(self, packet_on_wire, extra_packets=[]):
        """Calls write and expects to find a serialized version of p in
        the socket send buffer.

        Parameters
        -----------
        Mqtt"""
        buf = buffer_packet(packet_on_wire)
        num_bytes_sent = len(buf)
        for p in extra_packets:
            buf += buffer_packet(p)
        self.set_send_side_effect([num_bytes_sent])

        self.reactor.write()
        self.socket.send.assert_called_once_with(buf)
        self.socket.send.reset_mock()

    def send_packets(self, packets_on_wire, extra_packets=[]):
        """Calls write and expects to find a serialized version of p in
        the socket send buffer.

        Parameters
        -----------
        Mqtt"""
        buf = ''
        for p in packets_on_wire:
            buf += buffer_packet(p)

        num_bytes_sent = len(buf)
        for p in extra_packets:
            buf += buffer_packet(p)

        self.set_send_side_effect([num_bytes_sent])

        self.reactor.write()
        self.socket.send.assert_called_once_with(buf)
        self.socket.send.reset_mock()

    def recv_disconnect(self, exception):
        """Calls write and expects to find a serialized version of p in
        the socket send buffer.

        Parameters
        -----------
        Mqtt"""
        self.set_send_side_effect([exception])

        self.reactor.read()
        self.socket.recv.assert_called_once()
        self.socket.recv.reset_mock()

    def set_send_packet_drip_and_write(self, p):
        buf = buffer_packet(p)
        for b in buf[0:-1]:
            ec = errno.EWOULDBLOCK
            self.socket.send.side_effect = [1, socket.error(ec, os.strerror(ec))]
            self.reactor.write()
            self.socket.send.assert_called_once()
            self.socket.send.reset_mock()
            self.assertTrue(self.reactor.want_write())
            # TODO: Reactor wants read all the time it is writing!
            # Is this okay?
            # self.assertFalse(self.reactor.want_read())

        self.socket.send.side_effect = None
        self.socket.send.return_value = 1
        self.reactor.write()

        self.socket.send.assert_called_once()
        self.socket.send.reset_mock()
        self.assertFalse(self.reactor.want_write())

    def start_to_name_resolution(self):
        self.assertIn(self.reactor.state, INACTIVE_STATES)
        self.assertIn(self.reactor.sock_state, INACTIVE_SOCK_STATES)

        # Start called
        self.name_resolver_future.set_result(None)
        self.name_resolver_future.set_done(False)
        self.reactor.start()
        self.assertEqual(SocketState.name_resolution, self.reactor.sock_state)

    def start_to_connecting(self):
        self.assertTrue(self.reactor.state in INACTIVE_STATES)
        self.assertIn(self.reactor.sock_state, INACTIVE_SOCK_STATES)

        # Set up start call.
        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.socket.getsockopt.return_value = 0

        self.reactor.start()

        self.name_resolver.assert_called_once()
        self.name_resolver.reset_mock()
        self.socket.connect.assert_called_once_with(self.af_inet_name_resolution()[4])
        self.socket.connect.reset_mock()
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(SocketState.connecting, self.reactor.sock_state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

    def start_to_handshake(self):
        """
        1. Call start but socket does not immediately connect (connect returns EINPROGRESS).
        2. Socket becomes connected.
        3. MqttConnect is sent to server.
        """
        self.start_to_connecting()

        # Connect occurs
        self.socket.getsockopt.return_value = 0
        self.socket.do_handshake.side_effect = ssl.SSLWantWriteError()

        self.reactor.write()

        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(SocketState.handshake, self.reactor.sock_state)
        self.assertTrue(self.reactor.want_write())
        self.assertFalse(self.reactor.want_read())

        self.socket.do_handshake.side_effect = None
        self.socket.do_handshake.reset_mock()

    def start_to_connack(self, preflight_queue=[]):
        """
        1. Call start but socket does not immediately connect (connect returns EINPROGRESS).
        2. Socket becomes connected.
        3. MqttConnect is sent to server.
        """
        self.start_to_handshake()

        connect = MqttConnect(self.client_id, self.properties.clean_session, self.keepalive_period)
        buf = buffer_packet(connect)
        for p in preflight_queue:
            buf += buffer_packet(p)
        self.set_send_side_effect([len(buf)])

        self.reactor.write()
        self.socket.send.assert_called_once_with(bytearray(buf))

        self.socket.send.reset_mock()

        self.assertEqual(self.reactor.state, ReactorState.starting)
        self.assertEqual(self.reactor.sock_state, SocketState.connected)
        self.assertEqual(self.reactor.mqtt_state, MqttState.connack)
        self.assertFalse(self.reactor.want_write())
        self.assertTrue(self.reactor.want_read())

    def start_to_immediate_connect(self):
        self.assertIn(self.reactor.state, INACTIVE_STATES)
        self.assertIn(self.reactor.sock_state, INACTIVE_SOCK_STATES)

        self.socket.connect.return_value = None
        connect = MqttConnect(self.client_id, self.properties.clean_session, self.keepalive_period)
        self.set_send_packet_side_effect(connect)
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.expected_sockaddr)
        self.socket.connect.reset_mock()
        self.assertTrue(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())
        self.reactor.write()
        self.socket.send.assert_called_once_with(buffer_packet(connect))
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(MqttState.connack, self.reactor.mqtt_state)
        self.assertEqual(SocketState.connected, self.reactor.sock_state)
        self.socket.send.reset_mock()

    def start_to_connected(self):
        """
        1. Call start
        2. Socket does not immediately connect (EINPROGRESS)
        3. Socket transmits connect
        4. Socket receives connack
        """
        self.start_to_connack()

        connack = MqttConnack(False, ConnackResult.accepted)
        self.recv_packet_then_ewouldblock(connack)
        self.assertEqual(ReactorState.started, self.reactor.state)
        self.assertEqual(SocketState.connected, self.reactor.sock_state)
        self.assertEqual(MqttState.connected, self.reactor.mqtt_state)
        self.assertFalse(self.reactor.want_write())
        self.assertTrue(self.reactor.want_read())

    def subscribe_and_suback(self, topics):
        """

        Parameters
        ----------
        topics: iterable of MqttTopic
        """

        # Push subscribe onto the wire.
        self.assertEqual(set(), self.reactor.send_packet_ids())
        subscribe = MqttSubscribe(0, topics)
        subscribe_ticket = self.reactor.subscribe(subscribe.topics)
        self.assertTrue(self.reactor.want_write())
        self.socket.send.assert_not_called()
        self.assertEqual(subscribe_ticket.status, MqttSubscribeStatus.preflight)
        self.assertEqual({subscribe.packet_id}, self.reactor.send_packet_ids())

        # Allow reactor to push subscribe onto the wire.
        self.set_send_packet_side_effect(subscribe)
        self.reactor.write()
        self.socket.send.assert_called_once_with(buffer_packet(subscribe))
        self.socket.send.reset_mock()
        self.on_suback.assert_not_called()
        self.assertEqual(subscribe_ticket.status, MqttSubscribeStatus.ack)

        # Feed reactor a suback
        suback = MqttSuback(subscribe.packet_id, [SubscribeResult(t.max_qos) for t in topics])
        self.recv_packet_then_ewouldblock(suback)
        self.assertEqual(self.reactor.state, ReactorState.started)
        self.assertEqual(self.reactor.sock_state, SocketState.connected)
        self.assertEqual(subscribe_ticket.status, MqttSubscribeStatus.done)
        self.on_suback.assert_called_once_with(self.reactor, suback)
        self.on_suback.reset_mock()
        self.assertEqual(set(), self.reactor.send_packet_ids())


class TestDnsResolution(TestReactor, unittest.TestCase):
    def test_sync_getaddrinfo_fail_eai_noname(self):
        self.assertTrue(self.reactor.state in INACTIVE_STATES)

        e = socket.gaierror(socket.EAI_NONAME, 'Name or service not known')
        self.name_resolver_future.set_exception(e)
        self.name_resolver_future.set_result(None)
        self.name_resolver_future.set_done(True)
        self.reactor.start()
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.on_connect_fail.assert_called_once()
        self.assertEqual(AddressReactorError(e), self.reactor.error)

    def test_sync_getaddrinfo_fail_nohost(self):
        self.assertTrue(self.reactor.state in INACTIVE_STATES)

        self.name_resolver_future.set_result([])
        self.reactor.start()
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.on_connect_fail.assert_called_once()

        e = socket.gaierror(socket.EAI_NONAME, 'Name or service not known')
        self.assertEqual(AddressReactorError(e), self.reactor.error)

    def test_async_getaddrinfo_fail_eai_noname(self):
        self.assertTrue(self.reactor.state in INACTIVE_STATES)

        e = socket.gaierror(socket.EAI_NONAME, 'Name or service not known')
        self.name_resolver_future.set_exception(e)
        self.name_resolver_future.set_result(None)
        self.name_resolver_future.set_done(False)
        self.reactor.start()
        self.assertEqual(SocketState.name_resolution, self.reactor.sock_state)

        self.on_connect_fail.assert_not_called()
        self.on_disconnect.assert_not_called()

        self.name_resolver_future.set_done(True)
        self.on_connect_fail.assert_called_once_with(self.reactor)
        self.on_disconnect.assert_not_called()
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertEqual(AddressReactorError(e), self.reactor.error)


class TestWillProperty(TestReactor, unittest.TestCase):
    def test_will_set_reset(self):
        self.assertIsNone(self.reactor.will)
        will = MqttWill(0, 'topic', 'payload', False)
        self.reactor.will = will
        self.assertEqual(will, self.reactor.will)
        self.reactor.will = None
        self.assertIsNone(self.reactor.will)

    def test_will_invalid_type(self):
        try:
            self.reactor.will = 1
            self.fail('Expected TypeError to be raised.')
        except TypeError:
            pass


class TestConnect(TestReactor, unittest.TestCase):
    def test_immediate_connect(self):
        self.start_to_immediate_connect()

        connack = MqttConnack(False, ConnackResult.accepted)
        self.recv_packet_then_ewouldblock(connack)
        self.assertEqual(ReactorState.started, self.reactor.state)

        self.reactor.terminate()

    def test_immediate_connect_socket_error(self):
        self.assertTrue(self.reactor.state in INACTIVE_STATES)

        e = errno.ECONNABORTED
        socket_error = socket.error(errno.ECONNABORTED, os.strerror(e))
        self.socket.connect.side_effect = socket_error
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.expected_sockaddr)
        self.socket.connect.reset_mock()
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertEqual(SocketReactorError(e), self.reactor.error)


class TestReactorPaths(TestReactor, unittest.TestCase):
    def test_start(self):
        self.start_to_connected()

        # Subscribe to topic
        topics = [MqttTopic('bear_topic', 1)]
        self.subscribe_and_suback(topics)

        # Publish new message
        p = MqttPublish(1, topics[0].name, 'outgoing', False, 1, False)
        self.set_send_packet_side_effect(p)
        self.reactor.publish(p.topic, p.payload, p.qos)
        self.socket.send.assert_not_called()
        self.assertTrue(self.reactor.want_write())
        self.reactor.write()
        self.assertFalse(self.reactor.want_write())
        self.socket.send.assert_called_once_with(buffer_packet(p))
        self.socket.send.reset_mock()

        # Acknowledge new message
        p = MqttPuback(p.packet_id)
        self.recv_packet_then_ewouldblock(p)
        self.socket.send.assert_not_called()

        publish = MqttPublish(1, topics[0].name, 'incoming', False, 1, False)
        puback = MqttPuback(p.packet_id)
        self.set_send_packet_side_effect(puback)
        self.recv_packet_then_ewouldblock(publish)
        self.reactor.write()
        self.on_publish.assert_called_once_with(self.reactor, publish)
        self.on_publish.reset_mock()
        self.socket.send.assert_called_once_with(buffer_packet(puback))

        self.reactor.terminate()

    def test_conn_and_connack_dripfeed(self):
        self.assertEqual(ReactorState.init, self.reactor.state)

        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.expected_sockaddr)
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(SocketState.connecting, self.reactor.sock_state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.set_send_packet_drip_and_write(MqttConnect(self.client_id, True, self.keepalive_period))
        self.assertEqual(self.reactor.state, ReactorState.starting)
        self.assertEqual(self.reactor.mqtt_state, MqttState.connack)

        connack = MqttConnack(False, ConnackResult.accepted)
        self.recv_packet_then_ewouldblock(connack)
        self.assertEqual(ReactorState.started, self.reactor.state)

        # Subscribe to topic
        topics = [MqttTopic('bear_topic', 1)]
        self.subscribe_and_suback(topics)

        p = MqttPublish(1, topics[0].name, 'outgoing', False, 1, False)
        self.set_send_packet_side_effect(p)
        self.reactor.publish(p.topic, p.payload, p.qos)
        self.reactor.write()
        self.socket.send.assert_called_once_with(buffer_packet(p))
        self.socket.send.reset_mock()

        p = MqttPuback(p.packet_id)
        self.recv_packet_then_ewouldblock(p)

        publish = MqttPublish(1, topics[0].name, 'incoming', False, 1, False)
        puback = MqttPuback(p.packet_id)
        self.set_send_packet_side_effect(puback)
        self.recv_packet_then_ewouldblock(publish)
        self.on_publish.assert_called_once_with(self.reactor, publish)
        self.on_publish.reset_mock()
        self.reactor.write()
        self.socket.send.assert_called_once_with(buffer_packet(puback))

        self.reactor.terminate()

    def test_recv_connect(self):
        self.start_to_connected()

        connect = MqttConnect('client', False, 0)
        self.recv_packet_then_ewouldblock(connect)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, DecodeReactorError))


class TestPacketsBeforeConnack(TestReactor, unittest.TestCase):
    def setUp(self):
        TestReactor.setUp(self)
        self.start_to_connack()

    def tearDown(self):
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, ProtocolReactorError))
        TestReactor.tearDown(self)

    def test_suback(self):
        self.recv_packet_then_ewouldblock(MqttSuback(0, [SubscribeResult.qos0]))

    def test_unsuback(self):
        self.recv_packet_then_ewouldblock(MqttUnsuback(0))

    def test_puback(self):
        self.recv_packet_then_ewouldblock(MqttPuback(0))

    def test_publish(self):
        self.recv_packet_then_ewouldblock(MqttPublish(0, 'topic_str', 'payload_bytes', False, 0, False))

    def test_pingresp(self):
        self.recv_packet_then_ewouldblock(MqttPingresp())

    def test_pingreq(self):
        self.recv_packet_then_ewouldblock(MqttPingreq())

    def test_pubrel(self):
        self.recv_packet_then_ewouldblock(MqttPubrel(0))

    def test_pubcomp(self):
        self.recv_packet_then_ewouldblock(MqttPubcomp(0))

    def test_pubrec(self):
        self.recv_packet_then_ewouldblock(MqttPubrec(0))


class TestPacketsBeforeConnackWhileMute(TestReactor, unittest.TestCase):
    def setUp(self):
        TestReactor.setUp(self)
        self.start_to_connack()
        self.reactor.stop()
        self.send_packet(MqttDisconnect())
        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

    def tearDown(self):
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, ProtocolReactorError))
        TestReactor.tearDown(self)

    def test_suback(self):
        self.recv_packet_then_ewouldblock(MqttSuback(0, [SubscribeResult.qos0]))

    def test_unsuback(self):
        self.recv_packet_then_ewouldblock(MqttUnsuback(0))

    def test_puback(self):
        self.recv_packet_then_ewouldblock(MqttPuback(0))

    def test_publish(self):
        self.recv_packet_then_ewouldblock(MqttPublish(0, 'topic_str', 'payload_bytes', False, 0, False))

    def test_pingresp(self):
        self.recv_packet_then_ewouldblock(MqttPingresp())

    def test_pingreq(self):
        self.recv_packet_then_ewouldblock(MqttPingreq())

    def test_pubrel(self):
        self.recv_packet_then_ewouldblock(MqttPubrel(0))

    def test_pubcomp(self):
        self.recv_packet_then_ewouldblock(MqttPubcomp(0))

    def test_pubrec(self):
        self.recv_packet_then_ewouldblock(MqttPubrec(0))


class TestConnackFail(TestReactor, unittest.TestCase):
    def test_connack_keepalive_timeout(self):
        self.start_to_connected()
        p = MqttPingreq()
        self.set_send_packet_side_effect(p)
        self.assertFalse(self.reactor.want_write())
        self.scheduler.poll(self.keepalive_period)
        self.assertTrue(self.reactor.want_write())
        self.reactor.write()
        self.assertFalse(self.reactor.want_write())
        self.socket.send.assert_called_once_with(buffer_packet(p))
        self.socket.send.reset_mock()

        self.scheduler.poll(self.keepalive_period * 0.5)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertEqual(self.reactor.error, KeepaliveTimeoutReactorError())

    def test_connack_unexpected_session_present(self):
        self.start_to_connack()

        connack = MqttConnack(True, ConnackResult.accepted)
        self.recv_packet_then_ewouldblock(connack)
        self.assertEqual(self.reactor.state, ReactorState.error)
        self.on_connack.assert_not_called()

    def test_connack_fail_codes(self):
        fail_codes = [r for r in ConnackResult if r != ConnackResult.accepted]
        fail_codes.sort()

        for fail_code in fail_codes:
            self.start_to_connack()

            connack = MqttConnack(False, fail_code)
            self.recv_packet_then_ewouldblock(connack)
            self.assertEqual(self.reactor.state, ReactorState.error)
            self.assertEqual(self.reactor.error, ConnectReactorError(fail_code))


class TestSubscribePath(TestReactor, unittest.TestCase):
    def start_to_subscribe(self):
        self.start_to_connected()

        # Create subscribe
        topics = [
            MqttTopic('topic1', 1),
            MqttTopic('topic2', 2),
        ]
        est = MqttSubscribeTicket(0, topics)
        subscribe_ticket = self.reactor.subscribe(topics)
        self.assertEqual(est, subscribe_ticket)

        self.send_packet(MqttSubscribe(est.packet_id, est.topics))

    def test_subscribe(self):
        """
        1. Call start
        2. Socket does not immediately connect (EINPROGRESS)
        3. Socket transmits connect
        4. Socket receives connack
        5. Creates subscribe
        6. Socket transmits subscribe.
        7. Socket receives suback.
        """
        self.start_to_subscribe()

        sp = MqttSuback(0, [SubscribeResult.qos1, SubscribeResult.qos2])
        self.recv_packet_then_ewouldblock(sp)
        self.assertEqual(ReactorState.started, self.reactor.state)

        self.reactor.terminate()

    def test_subscribe_bad_suback_packet_id(self):
        """
        1. Call start
        2. Socket does not immediately connect (EINPROGRESS)
        3. Socket transmits connect
        4. Socket receives connack
        5. Creates subscribe
        6. Socket transmits subscribe.
        7. Socket receives suback.
        """
        self.start_to_subscribe()

        sp = MqttSuback(1, [SubscribeResult.qos1, SubscribeResult.qos2])
        self.recv_packet_then_ewouldblock(sp)
        self.assertEqual(ReactorState.error, self.reactor.state)

        self.reactor.terminate()

    def test_subscribe_bad_num_suback_results(self):
        """
        1. Call start
        2. Socket does not immediately connect (EINPROGRESS)
        3. Socket transmits connect
        4. Socket receives connack
        5. Creates subscribe
        6. Socket transmits subscribe.
        7. Socket receives suback.
        """
        self.start_to_subscribe()

        sp = MqttSuback(0, [SubscribeResult.qos1])
        self.recv_packet_then_ewouldblock(sp)
        self.assertEqual(ReactorState.error, self.reactor.state)

        self.reactor.terminate()


class TestUnsubscribePath(TestReactor, unittest.TestCase):
    def start_to_unsubscribe(self):
        self.start_to_connected()

        # Create subscribe
        topics = [
            'topic1',
            'topic2',
        ]
        eut = MqttUnsubscribeTicket(0, topics)
        unsubscribe_ticket = self.reactor.unsubscribe(topics)
        self.assertEqual(eut, unsubscribe_ticket)

        self.send_packet(MqttUnsubscribe(eut.packet_id, eut.topics))

    def test_unsubscribe(self):
        self.start_to_unsubscribe()
        self.on_unsuback.assert_not_called()

        up = MqttUnsuback(0)
        self.recv_packet_then_ewouldblock(up)
        self.assertEqual(ReactorState.started, self.reactor.state)
        self.on_unsuback.assert_called_once()

        self.reactor.terminate()

    def test_unsubscribe_bad_suback_packet_id(self):
        self.start_to_unsubscribe()
        self.on_unsuback.assert_not_called()

        up = MqttUnsuback(1)
        self.recv_packet_then_ewouldblock(up)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.on_disconnect.assert_called_once()

        self.reactor.terminate()


class TestSendPathQos0(TestReactor, unittest.TestCase):
    def test_start_and_publish_qos0(self):
        """
        1. Call start
        2. Socket does not immediately connect (EINPROGRESS)
        3. Socket transmits connect
        4. Socket receives connack
        5. Publishes a QoS=0 packet;
        6. Calls write and places publish packet in-flight.

        Returns
        -------
        MqttPublishTicket
            The returned MqttPublishTicket will have its status set to
            :py:const:`MqttPublishStatus.done`.
        """
        # CHECKED-KC0 (2018-09-19)
        self.start_to_connected()

        # Create publish
        ept = MqttPublishTicket(0, 'topic', 'outgoing', 0)
        publish_ticket = self.reactor.publish(ept.topic,
                                              ept.payload,
                                              ept.qos,
                                              ept.retain)
        self.assertEqual(ept, publish_ticket)
        self.assertTrue(self.reactor.want_write())
        self.assertEqual(1, len(self.reactor.preflight_packets()))
        self.assertEqual(0, len(self.reactor.in_flight_packets()))
        self.assertEqual(1, len(self.reactor.send_packet_ids()))
        self.socket.send.assert_not_called()
        self.assertEqual(publish_ticket.status, MqttPublishStatus.preflight)

        # Write is called; reactor attempts to push packet to socket
        # send buffer.
        #
        publish = MqttPublish(0, ept.topic, ept.payload, ept.dupe, ept.qos, ept.retain)
        self.set_send_packet_side_effect(publish)
        self.reactor.write()
        self.assertEqual(publish_ticket.status, MqttPublishStatus.done)
        self.assertEqual(publish_ticket.packet_id, publish.packet_id)
        self.socket.send.assert_called_once_with(buffer_packet(publish))
        self.assertFalse(self.reactor.want_write())
        self.socket.send.reset_mock()
        self.assertEqual(0, len(self.reactor.preflight_packets()))
        self.assertEqual(0, len(self.reactor.in_flight_packets()))
        self.assertEqual(set(), self.reactor.send_packet_ids())

        self.reactor.terminate()


class TestSendPathQos1(TestReactor, unittest.TestCase):
    def reactor_properties(self):
        p = super(type(self), self).reactor_properties()
        p.clean_session = False
        return p

    def start_and_publish_qos1(self):
        """
        1. Call start
        2. Socket does not immediately connect (EINPROGRESS)
        3. Socket transmits connect
        4. Socket receives connack
        5. Publishes a QoS=1 packet;
        6. Calls write and places publish packet in-flight.

        Returns
        -------
        MqttPublishTicket
            The returned MqttPublishTicket will have its status set to
            :py:const:`MqttPublishStatus.puback`.
        """
        self.start_to_connected()

        # Create publish
        ept = MqttPublishTicket(0, 'topic', 'outgoing', 1)
        publish_ticket = self.reactor.publish(ept.topic,
                                              ept.payload,
                                              ept.qos,
                                              ept.retain)
        self.assertEqual(ept, publish_ticket)
        self.assertTrue(self.reactor.want_write())
        self.socket.send.assert_not_called()
        self.assertEqual(publish_ticket.status, MqttPublishStatus.preflight)
        self.assertEqual(1, len(self.reactor.preflight_packets()))
        self.assertEqual(0, len(self.reactor.in_flight_packets()))
        self.assertEqual({0}, self.reactor.send_packet_ids())

        # Write is called; reactor attempts to push packet to socket
        # send buffer.
        #
        publish = MqttPublish(0, ept.topic, ept.payload, ept.dupe, ept.qos, ept.retain)
        self.set_send_packet_side_effect(publish)
        self.reactor.write()
        self.assertEqual(publish_ticket.status, MqttPublishStatus.puback)
        self.assertEqual(publish_ticket.packet_id, publish.packet_id)
        self.socket.send.assert_called_once_with(buffer_packet(publish))
        self.assertFalse(self.reactor.want_write())
        self.socket.send.reset_mock()
        self.assertEqual(0, len(self.reactor.preflight_packets()))
        self.assertEqual(1, len(self.reactor.in_flight_packets()))
        self.assertEqual({0}, self.reactor.send_packet_ids())

        return publish_ticket

    def test_publish_qos1(self):
        # CHECKED-KC0 (2018-09-17)
        publish_ticket = self.start_and_publish_qos1()

        # Server sends puback back to reactor.
        puback = MqttPuback(publish_ticket.packet_id)
        self.recv_packet_then_ewouldblock(puback)
        self.on_puback.assert_called_once_with(self.reactor, puback)
        self.assertEqual(publish_ticket.status, MqttPublishStatus.done)
        self.assertEqual(ReactorState.started, self.reactor.state)
        self.assertEqual(0, len(self.reactor.preflight_packets()))
        self.assertEqual(0, len(self.reactor.in_flight_packets()))
        self.assertEqual(set(), self.reactor.send_packet_ids())

        self.reactor.terminate()

    def test_publish_qos1_puback_after_mute(self):
        # CHECKED-KC0 (2018-09-17)
        publish_ticket = self.start_and_publish_qos1()

        # Stop
        self.reactor.stop()
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        # Muted
        self.send_packet(MqttDisconnect())
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)

        # Receive puback after muted.
        self.assertEqual(publish_ticket.status, MqttPublishStatus.puback)
        puback = MqttPuback(publish_ticket.packet_id)
        self.recv_packet_then_ewouldblock(puback)
        self.on_puback.assert_called_once_with(self.reactor, puback)
        self.assertEqual(publish_ticket.status, MqttPublishStatus.done)
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(0, len(self.reactor.preflight_packets()))
        self.assertEqual(0, len(self.reactor.in_flight_packets()))
        self.assertEqual(set(), self.reactor.send_packet_ids())

        self.reactor.terminate()

    def test_publish_qos1_out_of_order_puback(self):
        # CHECKED-KC0 (2018-09-17)
        pt0 = self.start_and_publish_qos1()

        # Publish a new message.
        ept1 = MqttPublishTicket(1, 'topic1', 'outgoing1', 1)
        pt1 = self.reactor.publish(ept1.topic,
                                   ept1.payload,
                                   ept1.qos,
                                   ept1.retain)
        self.assertTrue(self.reactor.want_write())
        self.socket.send.assert_not_called()
        self.assertEqual(ept1, pt1)
        self.assertEqual(1, len(self.reactor.preflight_packets()))
        self.assertEqual(1, len(self.reactor.in_flight_packets()))
        self.assertEqual({0, 1}, self.reactor.send_packet_ids())

        # Allow reactor to put pt1 in-flight.
        publish = MqttPublish(1, pt1.topic, pt1.payload, pt1.dupe, pt1.qos, pt1.retain)
        self.set_send_packet_side_effect(publish)

        self.reactor.write()

        self.socket.send.assert_called_once_with(buffer_packet(publish))

        self.assertEqual(1, pt1.packet_id)
        self.assertEqual(MqttPublishStatus.puback, pt1.status)
        self.socket.send.reset_mock()
        self.assertEqual(ReactorState.started, self.reactor.state)
        self.assertEqual(0, len(self.reactor.preflight_packets()))
        self.assertEqual(2, len(self.reactor.in_flight_packets()))
        self.assertEqual({0, 1}, self.reactor.send_packet_ids())

        # Send a puback for pt1 to the reactor before a puback for pt0
        # is sent.  This is a violation of [MQTT-4.6.0-2].
        puback = MqttPuback(pt1.packet_id)
        self.recv_packet_then_ewouldblock(puback)
        self.on_puback.assert_not_called()
        self.assertEqual(self.reactor.state, ReactorState.error)

        self.reactor.terminate()

    def test_publish_qos1_pubrec(self):
        # CHECKED-KC0 (2018-09-17)
        publish_ticket = self.start_and_publish_qos1()

        puback = MqttPubrec(publish_ticket.packet_id)
        self.recv_packet_then_ewouldblock(puback)
        self.on_puback.assert_not_called()
        self.assertEqual(self.reactor.state, ReactorState.error)
        self.assertEqual(publish_ticket.status, MqttPublishStatus.puback)

        self.reactor.terminate()

    def test_puback_not_in_flight(self):
        # CHECKED-KC0 (2018-09-17)

        self.start_to_connected()

        puback = MqttPuback(0)
        self.recv_packet_then_ewouldblock(puback)
        self.on_puback.assert_not_called()
        self.assertEqual(self.reactor.state, ReactorState.error)
        self.assertEqual(0, len(self.reactor.preflight_packets()))
        self.assertEqual(0, len(self.reactor.in_flight_packets()))
        self.assertEqual(set(), self.reactor.send_packet_ids())

    def test_publish_disconnect_connect_republish_qos1(self):
        # CHECKED-KC0 (2018-09-17)
        publish_ticket = self.start_and_publish_qos1()

        # Terminate
        self.reactor.terminate()
        self.assertEqual(ReactorState.stopped, self.reactor.state)
        self.assertFalse(publish_ticket.dupe)

        # Start a new connection which does not immediately connect.
        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.expected_sockaddr)
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(SocketState.connecting, self.reactor.sock_state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())
        self.assertTrue(publish_ticket.dupe)  # dupe flag set on publish ticket.
        self.assertEqual(1, len(self.reactor.preflight_packets()))
        self.assertEqual(0, len(self.reactor.in_flight_packets()))
        self.assertEqual({0}, self.reactor.send_packet_ids())

        # Socket connects and reactor sends a MqttConnect packet.
        publish = publish_ticket.packet()

        self.socket.getsockopt.return_value = 0
        self.send_packets([MqttConnect(self.client_id, self.properties.clean_session, self.keepalive_period), publish])
        self.assertEqual(self.reactor.state, ReactorState.starting)
        self.assertEqual(self.reactor.mqtt_state, MqttState.connack)

        # Receives connack.
        connack = MqttConnack(False, ConnackResult.accepted)
        self.recv_packet_then_ewouldblock(connack)

        self.assertEqual(0, len(self.reactor.preflight_packets()))
        self.assertEqual(1, len(self.reactor.in_flight_packets()))
        self.assertEqual({0}, self.reactor.send_packet_ids())
        self.assertTrue(publish_ticket.dupe)
        self.assertEqual(self.reactor.state, ReactorState.started)
        self.socket.send.assert_not_called()
        self.assertFalse(self.reactor.want_write())
        self.assertEqual(publish_ticket.status, MqttPublishStatus.puback)

        self.reactor.terminate()


class TestSendPathQos2(TestReactor, unittest.TestCase):
    def reactor_properties(self):
        p = super(type(self), self).reactor_properties()
        p.clean_session = False
        return p

    def start_and_publish_qos2(self):
        self.start_to_connected()

        publish = MqttPublish(0, 'topic', 'outgoing', False, 2, False)
        pub_status = MqttPublishTicket(0, publish.topic, publish.payload, publish.qos, publish.retain)
        self.set_send_packet_side_effect(publish)
        actual_publish = self.reactor.publish(publish.topic,
                                       publish.payload,
                                       publish.qos,
                                       publish.retain)
        self.assertTrue(self.reactor.want_write())
        self.assertEqual(pub_status, actual_publish)
        self.reactor.write()
        self.socket.send.reset_mock()

        return publish

    def test_publish_qos2(self):
        publish = self.start_and_publish_qos2()

        pubrec = MqttPubrec(publish.packet_id)
        pubrel = MqttPubrel(publish.packet_id)
        self.set_send_packet_side_effect(pubrel)
        self.recv_packet_then_ewouldblock(pubrec)
        self.on_pubrec.assert_called_once()
        self.reactor.write()
        self.socket.send.assert_called_once_with(buffer_packet(pubrel))
        self.socket.send.reset_mock()

        pubcomp = MqttPubcomp(publish.packet_id)
        self.recv_packet_then_ewouldblock(pubcomp)
        self.on_pubcomp.assert_called_once()
        self.socket.send.assert_not_called()

        self.reactor.terminate()

    def test_publish_qos2_out_of_order_pubrec(self):
        self.start_and_publish_qos2()

        publish = MqttPublish(1, 'topic', 'outgoing', False, 2, False)
        self.set_send_packet_side_effect(publish)
        actual_publish = self.reactor.publish(publish.topic,
                                       publish.payload,
                                       publish.qos,
                                       publish.retain)
        self.socket.send.reset_mock()
        self.assertTrue(self.reactor.want_write())

        pubrec = MqttPubrec(publish.packet_id)
        self.recv_packet_then_ewouldblock(pubrec)
        self.on_pubrec.assert_not_called()
        self.socket.send.assert_not_called()
        self.socket.send.reset_mock()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_publish_qos2_out_of_order_pubcomp(self):
        publish0 = self.start_and_publish_qos2()

        # on-the-wire
        #
        # C --MqttPublish(packet_id=0, topic='topic', payload=0x6f7574676f696e67, dupe=False, qos=2, retain=False)--> S
        #
        publish1 = MqttPublish(1, 'topic', 'outgoing', False, 2, False)
        pub_status = MqttPublishTicket(1, publish1.topic, publish1.payload, publish1.qos, publish1.retain)
        actual_publish = self.reactor.publish(publish1.topic,
                                       publish1.payload,
                                       publish1.qos,
                                       publish1.retain)
        # publish is queued
        self.set_send_packet_side_effect(publish1)
        self.assertTrue(self.reactor.want_write())
        self.reactor.write()

        # on-the-wire
        #
        # C --MqttPublish(packet_id=1, topic='topic', payload=0x6f7574676f696e67, dupe=False, qos=2, retain=False)--> S
        #
        self.socket.send.reset_mock()
        self.assertFalse(self.reactor.want_write())
        pub_status._set_status(MqttPublishStatus.pubrec)
        self.assertEqual(pub_status, actual_publish)

        pubrec0 = MqttPubrec(publish0.packet_id)
        pubrel0 = MqttPubrel(publish0.packet_id)
        self.set_send_packet_side_effect([pubrel0])
        #
        # on-the-wire
        #
        # C --MqttPublish(packet_id=1, topic='topic', payload=0x6f7574676f696e67, dupe=False, qos=2, retain=False)--> S
        #
        self.recv_packet_then_ewouldblock(pubrec0)
        self.on_pubrec.assert_called_once(); self.on_pubrec.reset_mock()
        self.assertTrue(self.reactor.want_write())
        self.reactor.write()
        self.socket.send.assert_called_once_with(buffer_packet(pubrel0))
        self.socket.send.reset_mock()
        self.assertEqual(self.reactor.state, ReactorState.started)

        pubrec1 = MqttPubrec(publish1.packet_id)
        pubrel1 = MqttPubrel(publish1.packet_id)
        self.set_send_packet_side_effect([pubrel1])
        self.recv_packet_then_ewouldblock(pubrec1)
        self.reactor.write()
        self.on_pubrec.assert_called_once(); self.on_pubrec.reset_mock()
        self.socket.send.assert_called_once_with(buffer_packet(pubrel1))
        self.socket.send.reset_mock()
        self.assertEqual(self.reactor.state, ReactorState.started)

        pubrec = MqttPubcomp(publish1.packet_id)
        self.recv_packet_then_ewouldblock(pubrec)
        self.on_pubrec.assert_not_called()
        self.socket.send.assert_not_called()
        self.socket.send.reset_mock()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_pubcomp_not_in_flightpublish_qos2_out_of_order_pubcomp(self):
        self.start_to_connected()

        pubcomp = MqttPubcomp(0)
        self.recv_packet_then_ewouldblock(pubcomp)
        self.on_pubcomp.assert_not_called()
        self.socket.send.assert_not_called()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_pubrec_not_in_flight_packet_id(self):
        self.start_to_connected()

        pubrec = MqttPubrec(0)
        self.recv_packet_then_ewouldblock(pubrec)
        self.on_pubrec.assert_not_called()
        self.socket.send.assert_not_called()
        self.socket.send.reset_mock()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_publish_qos2_puback_error(self):
        publish = self.start_and_publish_qos2()

        puback = MqttPuback(publish.packet_id)
        self.recv_packet_then_ewouldblock(puback)
        self.socket.send.assert_not_called()
        self.socket.send.reset_mock()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_publish_disconnect_qos2(self):
        self.start_to_connected()

        publish = MqttPublish(0, 'topic', 'incoming', False, 2, False)
        pub_status = MqttPublishTicket(0, publish.topic, publish.payload, publish.qos, publish.retain)
        se = socket_error(errno.ECONNABORTED)
        self.set_send_side_effect([se])
        self.assertFalse(self.reactor.want_write())
        actual_publish = self.reactor.publish(publish.topic,
                                       publish.payload,
                                       publish.qos,
                                       publish.retain)
        self.assertTrue(self.reactor.want_write())
        self.reactor.write()
        self.assertEqual(pub_status, actual_publish)
        self.assertEqual(self.reactor.state, ReactorState.error)
        self.assertEqual(self.reactor.error, SocketReactorError(se.errno))
        self.socket.send.reset_mock()

        self.start_to_connack(preflight_queue=[publish])

        connack = MqttConnack(False, ConnackResult.accepted)
        self.set_send_packet_side_effect(publish)
        self.recv_packet_then_ewouldblock(connack)
        self.assertEqual(self.reactor.state, ReactorState.started)

        pubrec = MqttPubrec(publish.packet_id)
        pubrel = MqttPubrel(publish.packet_id)
        self.set_send_packet_side_effect(pubrel)
        self.recv_packet_then_ewouldblock(pubrec)
        self.on_pubrec.assert_called_once()
        self.reactor.write()
        self.socket.send.assert_called_once_with(buffer_packet(pubrel))
        self.socket.send.reset_mock()

        pubcomp = MqttPubcomp(publish.packet_id)
        self.recv_packet_then_ewouldblock(pubcomp)
        self.on_pubcomp.assert_called_once()
        self.socket.send.assert_not_called()

        self.reactor.terminate()

    def test_pubrel_disconnect_qos2(self):
        self.start_to_connected()

        publish = MqttPublish(0, 'topic', 'incoming', False, 2, False)
        self.set_send_packet_side_effect(publish)
        actual_publish = self.reactor.publish(publish.topic,
                                       publish.payload,
                                       publish.qos,
                                       publish.retain)
        self.assertTrue(self.reactor.want_write())
        self.reactor.write()
        self.socket.send.reset_mock()

        pubrec = MqttPubrec(publish.packet_id)
        pubrel = MqttPubrel(publish.packet_id)
        se = socket_error(errno.ECONNABORTED)
        self.set_send_side_effect([se])
        self.recv_packet_then_ewouldblock(pubrec)
        self.on_pubrec.assert_called_once()
        self.reactor.write()
        self.socket.send.assert_called_once_with(buffer_packet(pubrel))
        self.socket.send.reset_mock()

        self.assertEqual(self.reactor.state, ReactorState.error)
        self.assertEqual(self.reactor.error, SocketReactorError(se.errno))

        self.start_to_connack(preflight_queue=[pubrel])

        connack = MqttConnack(False, ConnackResult.accepted)
        self.recv_packet_then_ewouldblock(connack)
        self.assertEqual(self.reactor.state, ReactorState.started)

        pubcomp = MqttPubcomp(publish.packet_id)
        self.recv_packet_then_ewouldblock(pubcomp)
        self.on_pubcomp.assert_called_once()
        self.socket.send.assert_not_called()

        self.assertEqual(self.reactor.state, ReactorState.started)

        self.reactor.terminate()


class TestReceivePathQos0(TestReactor, unittest.TestCase):
    def test_recv_publish(self):
        self.start_to_connected()

        topics = [MqttTopic('bear_topic', 0)]
        self.subscribe_and_suback(topics)

        # Receive QoS=0 publish
        publish = MqttPublish(1, topics[0].name, 'incoming', False, topics[0].max_qos, False)
        self.set_send_side_effect([len(buffer_packet(publish))])
        self.recv_packet_then_ewouldblock(publish)
        self.on_publish.assert_called_once()
        self.assertFalse(self.reactor.want_write())
        self.socket.send.assert_not_called()

        # Immediate shut-down.
        self.reactor.terminate()

    def test_mute_recv_publish(self):
        self.start_to_connected()
        self.reactor.stop()
        self.send_packet(MqttDisconnect())
        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        # Receive QoS=0 publish
        publish = MqttPublish(1, 'topic', 'payload', False, 1, False)
        self.set_send_side_effect([len(buffer_packet(publish))])
        self.recv_packet_then_ewouldblock(publish)
        self.on_publish.assert_called_once()
        self.assertFalse(self.reactor.want_write())
        self.socket.send.assert_not_called()

        # Immediate shut-down.
        self.reactor.terminate()

    def test_publish_before_connack(self):
        self.start_to_connack()

        # Receive QoS=0 publish
        publish = MqttPublish(1, 'topic', 'payload', False, 1, False)
        self.set_send_side_effect([len(buffer_packet(publish))])
        self.recv_packet_then_ewouldblock(publish)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, ProtocolReactorError))

    def test_mute_publish_before_connack(self):
        self.start_to_connack()
        self.reactor.stop()
        self.send_packet(MqttDisconnect())
        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        # Receive QoS=0 publish
        publish = MqttPublish(1, 'topic', 'payload', False, 1, False)
        self.set_send_side_effect([len(buffer_packet(publish))])
        self.recv_packet_then_ewouldblock(publish)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, ProtocolReactorError))


class TestReceivePathQos1(TestReactor, unittest.TestCase):
    def test_recv_publish(self):
        self.start_to_connected()

        topics = [MqttTopic('bear_topic', 1)]
        self.subscribe_and_suback(topics)

        self.on_publish.assert_not_called()
        publish = MqttPublish(1, topics[0].name, 'incoming', False, topics[0].max_qos, False)
        self.set_send_side_effect([len(buffer_packet(publish))])
        self.recv_packet_then_ewouldblock(publish)
        self.on_publish.assert_called_once()

        puback = MqttPuback(publish.packet_id)
        self.reactor.write()
        self.socket.send.assert_called_once_with(buffer_packet(puback))
        self.socket.send.reset_mock()

        self.reactor.terminate()


class TestReceivePathQos2(TestReactor, unittest.TestCase):
    def test_recv_publish(self):
        self.start_to_connected()

        topics = [MqttTopic('bear_topic', 2)]
        self.subscribe_and_suback(topics)

        self.on_publish.assert_not_called()
        publish = MqttPublish(1, topics[0].name, 'outgoing', False, topics[0].max_qos, False)
        self.set_send_side_effect([len(buffer_packet(publish))])
        self.recv_packet_then_ewouldblock(publish)
        self.on_publish.assert_called_once()

        pubrec = MqttPubrec(publish.packet_id)
        self.reactor.write()
        self.socket.send.assert_called_once_with(buffer_packet(pubrec))
        self.socket.send.reset_mock()

        self.on_pubrel.assert_not_called()
        pubrel = MqttPubrel(publish.packet_id)
        pubcomp = MqttPubcomp(publish.packet_id)
        self.set_send_side_effect([len(buffer_packet(pubcomp))])
        self.recv_packet_then_ewouldblock(pubrel)
        self.assertEqual(ReactorState.started, self.reactor.state)
        self.on_pubrel.assert_called_once()

        pubcomp = MqttPubcomp(publish.packet_id)
        self.reactor.write()
        self.socket.send.assert_called_once_with(buffer_packet(pubcomp))
        self.socket.send.reset_mock()

        self.reactor.terminate()


class TestReactorPeerDisconnect(TestReactor, unittest.TestCase):
    def test_connect(self):
        self.assertEqual(self.reactor.state, ReactorState.init)
        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.expected_sockaddr)
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(SocketState.connecting, self.reactor.sock_state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.set_send_side_effect([socket.error(errno.EPIPE, os.strerror(errno.EPIPE))])
        self.reactor.write()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_connack(self):
        self.assertEqual(self.reactor.state, ReactorState.init)
        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.expected_sockaddr)
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(SocketState.connecting, self.reactor.sock_state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.send_packet(MqttConnect(self.client_id, True, self.keepalive_period))
        self.assertEqual(self.reactor.state, ReactorState.starting)
        self.assertEqual(self.reactor.mqtt_state, MqttState.connack)

        self.set_recv_side_effect([''])
        self.reactor.read()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_connected(self):
        self.assertEqual(self.reactor.state, ReactorState.init)
        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.expected_sockaddr)
        self.assertEqual(SocketState.connecting, self.reactor.sock_state)
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.send_packet(MqttConnect(self.client_id, True, self.keepalive_period))
        self.assertEqual(self.reactor.state, ReactorState.starting)
        self.assertEqual(self.reactor.mqtt_state, MqttState.connack)

        self.recv_packet_then_ewouldblock(MqttConnack(False, ConnackResult.accepted))
        self.assertEqual(ReactorState.started, self.reactor.state)
        self.assertEqual(SocketState.connected, self.reactor.sock_state)

        self.set_recv_side_effect([''])
        self.reactor.read()


class TestReactorStart(TestReactor, unittest.TestCase):
    def test_name_resolution(self):
        self.start_to_name_resolution()
        self.reactor.start()
        self.assertEqual(SocketState.name_resolution, self.reactor.sock_state)
        self.reactor.terminate()

    def test_connecting(self):
        self.start_to_connecting()
        self.reactor.start()
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(SocketState.connecting, self.reactor.sock_state)
        self.reactor.terminate()

    def test_handshake(self):
        self.start_to_handshake()
        self.reactor.start()
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(SocketState.handshake, self.reactor.sock_state)
        self.reactor.terminate()

    def test_connack(self):
        self.start_to_connack()
        self.reactor.start()
        self.assertEqual(MqttState.connack, self.reactor.mqtt_state)
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.reactor.terminate()

    def test_connected(self):
        self.start_to_connected()
        self.reactor.start()
        self.assertEqual(ReactorState.started, self.reactor.state)
        self.reactor.terminate()

    def test_mute(self):
        self.start_to_connected()
        self.reactor.stop()
        #self.reactor.read()
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(SocketState.connected, self.reactor.sock_state)
        self.send_packet(MqttDisconnect())
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.reactor.start()
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.reactor.terminate()


class TestReactorStop(TestReactor, unittest.TestCase):
    def test_init(self):
        self.assertEqual(ReactorState.init, self.reactor.state)
        self.reactor.stop()
        self.assertEqual(ReactorState.stopped, self.reactor.state)

    def test_name_resolution_error_and_stop_on_error(self):
        self.start_to_name_resolution()

        # DNS resolved
        e = socket.gaierror(socket.EAI_NONAME, 'Name or service not known')
        self.name_resolver_future.set_exception(e)
        self.name_resolver_future.set_result(None)
        self.name_resolver_future.set_done(True)
        self.on_connect_fail.assert_called_once_with(self.reactor)
        self.on_disconnect.assert_not_called()
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertEqual(AddressReactorError(e), self.reactor.error)

        # Verify that stop has no effect.
        self.reactor.stop()
        self.assertEqual(ReactorState.error, self.reactor.state)

    def test_name_resolution_stop(self):
        self.assertTrue(self.reactor.state in INACTIVE_STATES)

        # Start called
        self.name_resolver_future.set_done(False)
        self.reactor.start()
        self.assertEqual(SocketState.name_resolution, self.reactor.sock_state)

        # Stop request
        self.reactor.stop()
        self.on_connect_fail.assert_called_once_with(self.reactor)
        self.on_disconnect.assert_not_called()
        self.assertEqual(ReactorState.stopped, self.reactor.state)

    def test_connecting(self):
        self.assertTrue(self.reactor.state in INACTIVE_STATES)

        # Start with async connect
        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(SocketState.connecting, self.reactor.sock_state)

        # Stop should have immediate effect at this point.
        self.reactor.stop()
        self.assertEqual(ReactorState.stopped, self.reactor.state)

    def test_handshake(self):
        self.start_to_handshake()

        # Stop should have immediate effect at this point.
        self.reactor.stop()
        self.assertEqual(ReactorState.stopped, self.reactor.state)

    def test_connack_empty_preflight(self):
        self.assertTrue(self.reactor.state in INACTIVE_STATES)

        # Start with async connect
        self.start_to_connack()

        # Verify that stop has no effect.
        self.reactor.stop()
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(MqttState.connack, self.reactor.mqtt_state)

        # Disconnect packet should be launched.
        disconnect = MqttDisconnect()
        self.send_packet(disconnect)
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)

        # Receives connack;
        connack = MqttConnack(False, ConnackResult.accepted)
        self.recv_packet_then_ewouldblock(connack)
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)

        # Server processes disconnect and sends mute of its own.
        self.recv_eof()

    def test_connack_with_preflight(self):
        self.assertTrue(self.reactor.state in INACTIVE_STATES)

        pub_ticket = self.reactor.publish('topic', 'payload', 1)

        # Start with async connect
        self.start_to_connack(preflight_queue=[pub_ticket.packet()])

        # Verify that stop has no effect.
        self.reactor.stop()
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(MqttState.connack, self.reactor.mqtt_state)

        # Send disconnect packet
        disconnect = MqttDisconnect()
        self.send_packet(disconnect)

        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        connack = MqttConnack(False, ConnackResult.accepted)
        self.recv_packet_then_ewouldblock(connack)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        puback = MqttPuback(pub_ticket.packet_id)
        self.recv_packet_then_ewouldblock(puback)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        self.recv_eof()
        self.assertEqual(SocketState.stopped, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopped, self.reactor.state)

    def test_recv_connack_while_mute(self):
        self.start_to_connack()
        self.reactor.stop()

        disconnect = MqttDisconnect()
        self.send_packet(disconnect)

        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        self.recv_packet_then_ewouldblock(MqttConnack(False, ConnackResult.accepted))
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)

        self.recv_eof()
        self.assertEqual(ReactorState.stopped, self.reactor.state)

    def test_recv_double_connack_while_mute(self):
        self.start_to_connack()
        self.reactor.stop()

        disconnect = MqttDisconnect()
        self.send_packet(disconnect)

        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        self.recv_packet_then_ewouldblock(MqttConnack(False, ConnackResult.accepted))
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)

        self.recv_packet_then_ewouldblock(MqttConnack(False, ConnackResult.accepted))
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, ProtocolReactorError))

    def test_connected_with_empty_preflight(self):
        self.start_to_connected()
        self.reactor.stop()

        disconnect = MqttDisconnect()
        self.send_packet(disconnect)

        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        self.recv_eof()
        self.assertEqual(ReactorState.stopped, self.reactor.state)

    def test_connected_double_stop(self):
        self.start_to_connected()
        self.assertEqual(ReactorState.started, self.reactor.state)
        self.reactor.stop()
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.reactor.stop()
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        disconnect = MqttDisconnect()
        self.send_packet(disconnect)

        self.assertEqual(SocketState.mute, self.reactor.sock_state)

        self.recv_eof()
        self.assertEqual(ReactorState.stopped, self.reactor.state)

    def test_mute(self):
        self.start_to_connected()
        self.reactor.stop()

        disconnect = MqttDisconnect()
        self.send_packet(disconnect)

        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.reactor.stop()

        self.recv_eof()
        self.assertEqual(ReactorState.stopped, self.reactor.state)

    def test_stopped(self):
        self.reactor.stop()
        self.assertEqual(ReactorState.stopped, self.reactor.state)
        self.reactor.stop()
        self.assertEqual(ReactorState.stopped, self.reactor.state)

    def test_error(self):
        self.socket.connect.side_effect = socket_error(errno.ECONNREFUSED)
        self.reactor.start()
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.reactor.stop()
        self.assertEqual(ReactorState.error, self.reactor.state)


class TestKeepaliveTimeout(TestReactor, unittest.TestCase):
    def test_handshake(self):
        # Start with async connect
        self.start_to_handshake()

        self.scheduler.poll(self.reactor.keepalive_timeout_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, KeepaliveTimeoutReactorError))

    def test_connack(self):
        # Start with async connect
        self.start_to_connack()

        self.scheduler.poll(self.reactor.keepalive_timeout_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, KeepaliveTimeoutReactorError))

    def test_connected(self):
        self.start_to_connected()

        self.scheduler.poll(self.reactor.keepalive_timeout_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, KeepaliveTimeoutReactorError))

    def test_mute(self):
        self.start_to_connected()
        self.reactor.stop()

        disconnect = MqttDisconnect()
        self.send_packet(disconnect)

        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        self.scheduler.poll(self.reactor.keepalive_timeout_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, KeepaliveTimeoutReactorError))


class TestPingreqPingresp(TestReactor, unittest.TestCase):
    def test_connack(self):
        # Start with async connect
        self.start_to_connack()

        # Verify waiting for connack and no writes are needed
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(MqttState.connack, self.reactor.mqtt_state)
        self.assertFalse(self.reactor.want_write())

        # Before a connack is received no pingreq should be sent.
        self.scheduler.poll(self.reactor.keepalive_period)
        self.assertFalse(self.reactor.want_write())

        # A pingreq is an error at this point.
        self.recv_packet_then_ewouldblock(MqttPingresp())
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, ProtocolReactorError))

    def test_connected(self):
        self.start_to_connected()

        # Send pingreq
        self.scheduler.poll(self.reactor.keepalive_period)
        self.assertEqual(ReactorState.started, self.reactor.state)
        self.send_packet(MqttPingreq())

        # Feed pingresp
        self.recv_packet_then_ewouldblock(MqttPingresp())
        self.assertEqual(ReactorState.started, self.reactor.state)

        # There have been `2 x keepalive_periods` that have passed in
        # the test.  Since `keepalive_timeout_period = 1.5 x keepalive_period`
        # then a keepalive error would have resulted if the pingresp
        # were not processed accurately.
        self.scheduler.poll(self.reactor.keepalive_period)
        self.assertEqual(ReactorState.started, self.reactor.state)

        self.reactor.terminate()

    def test_connected_unsolicited_pingresp(self):
        self.start_to_connected()

        # Feed unsolicited pingresp; should be ignored.
        self.recv_packet_then_ewouldblock(MqttPingresp())
        self.assertEqual(ReactorState.started, self.reactor.state)

        self.reactor.terminate()

    def test_mute(self):
        self.start_to_connected()

        # Send pingreq
        self.scheduler.poll(self.reactor.keepalive_period)
        self.assertEqual(ReactorState.started, self.reactor.state)
        self.send_packet(MqttPingreq())

        # Reactor is stopped before receiving the pingresp.
        self.reactor.stop()

        disconnect = MqttDisconnect()
        self.send_packet(disconnect)

        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        # Feed pingresp
        self.recv_packet_then_ewouldblock(MqttPingresp())
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)

        # There have been `2 x keepalive_periods` that have passed in
        # the test.  Since `keepalive_timeout_period = 1.5 x keepalive_period`
        # then a keepalive error would have resulted if the pingresp
        # were not processed accurately.
        self.scheduler.poll(self.reactor.keepalive_period)
        self.assertEqual(ReactorState.stopping, self.reactor.state)
        self.assertEqual(SocketState.mute, self.reactor.sock_state)

        self.recv_eof()
        self.assertEqual(ReactorState.stopped, self.reactor.state, self.reactor.error)
