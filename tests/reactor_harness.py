from __future__ import print_function

import errno
import logging
import os
import socket
import ssl
import sys
import unittest
from io import BytesIO

from mock import Mock
from time import gmtime

from haka_mqtt.clock import SettableClock
from haka_mqtt.mqtt_request import MqttSubscribeStatus
from haka_mqtt.reactor import ReactorProperties, Reactor, INACTIVE_STATES, INACTIVE_SOCK_STATES, SocketState, \
    ReactorState, MqttState
from haka_mqtt.scheduler import DurationScheduler
from mqtt_codec.packet import MqttConnect, MqttConnack, ConnackResult, MqttSubscribe, MqttSuback, SubscribeResult


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


P3K = sys.version_info.major >= 3


class ClockLogger(logging.Logger):
    clock = None
    start_time = None

    def __init__(self, name, level=logging.NOTSET):
        logging.Logger.__init__(self, name, level=level)

    if P3K:
        def makeRecord(self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None):
            log_record = super(type(self), self).makeRecord(name, level, fn, lno, msg, args, exc_info,
                                                            func=func, extra=extra, sinfo=sinfo)
            ct = ClockLogger.clock.time()
            log_record.created = ct
            log_record.msecs = (ct - int(log_record.created)) * 1000
            log_record.relativeCreated = (log_record.created - ClockLogger.start_time) * 1000
            return log_record
    else:
        def makeRecord(self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None):
            log_record = super(type(self), self).makeRecord(name, level, fn, lno, msg, args, exc_info,
                                                            func=func, extra=extra)
            ct = ClockLogger.clock.time()
            log_record.created = ct
            log_record.msecs = (ct - int(log_record.created)) * 1000
            log_record.relativeCreated = (log_record.created - ClockLogger.start_time) * 1000
            return log_record


class ClockDurationScheduler(DurationScheduler):
    def __init__(self, clock):
        DurationScheduler.__init__(self)
        self.__clock = clock

    def poll(self, duration):
        """Adds `duration` to `self.instant()` and calls all scheduled
        callbacks.

        Parameters
        ----------
        duration: int
        """
        self.__clock.add_time(duration)
        DurationScheduler.poll(self, duration)


class TestReactor(unittest.TestCase):
    def reactor_properties(self):
        p = ReactorProperties()
        p.socket_factory = lambda getaddrinfo_params, sockaddr: self.socket
        p.endpoint = self.endpoint
        p.client_id = self.client_id
        p.keepalive_period = self.keepalive_period
        p.scheduler = self.scheduler
        p.clean_session = True
        p.name_resolver = self.name_resolver
        p.recv_idle_ping_period = self.recv_idle_ping_period
        p.recv_idle_abort_period = self.recv_idle_abort_period

        return p

    def setup_logging(self):
        self._saved_logging_class = logging.getLoggerClass()
        ClockLogger.clock = self.clock
        ClockLogger.start_time = self.clock.time()

        logging.Formatter.converter = gmtime
        logging.setLoggerClass(ClockLogger)

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

        ClockLogger.clock = None
        ClockLogger.start_time = None
        logging.setLoggerClass(self._saved_logging_class)

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
        self.clock = SettableClock()
        self.clock.set_time(946684800.)

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
        self.recv_idle_ping_period = 10*60
        self.recv_idle_abort_period = 15*60
        self.scheduler = ClockDurationScheduler(self.clock)

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
        """Calls ``self.reactor.write`` and expects to find a serialized
        version of p in the socket send buffer.

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
        buf = b''
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

    def poll(self, period):
        while period > 0:
            poll_period = self.scheduler.remaining()
            if poll_period > period:
                poll_period = period
            self.scheduler.poll(poll_period)
            period -= poll_period
