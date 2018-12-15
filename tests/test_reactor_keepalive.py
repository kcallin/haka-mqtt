import unittest

from haka_mqtt.reactor import ReactorState, MqttState, ProtocolReactorError, SocketState, RecvTimeoutReactorError
from mqtt_codec.packet import MqttPingresp, MqttPingreq, MqttDisconnect, MqttTopic, MqttPublish, MqttConnack, \
    ConnackResult
from tests.reactor_harness import TestReactor


"""
rule:
Only one MqttPingreq may be in preflight at any given time.


send path:

await_connack and keepalive is due.

Another keepalive comes due.
Another keepalive comes due.

deaf when keepalive comes due?


recv ping path:

await connack, ping due (do not send)
deaf and keepalive comes due. (do not send)
mute and keepalive comes due. (do not send)
"""


class TestKeepalive(TestReactor, unittest.TestCase):
    def reactor_properties(self):
        self.keepalive_period = 7  # Set keepalive period so that it dominates.
        self.recv_idle_ping_period = 8
        self.recv_idle_abort_period = 17
        return TestReactor.reactor_properties(self)

    def test_connack(self):
        # Start with async connect
        self.start_to_connack()

        min_time_step = 0.001
        # Verify waiting for connack and no writes are needed
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(MqttState.connack, self.reactor.mqtt_state)
        self.assertFalse(self.reactor.want_write())

        # Before a connack is received no pingreq should be sent.  Any
        # keepalive should be deferred until after the connack is
        # received.
        self.scheduler.poll(self.reactor.keepalive_period)
        self.assertFalse(self.reactor.want_write())

        # Receive connack and then launch deferred pingreq.
        self.recv_packet_then_ewouldblock(MqttConnack(False, ConnackResult.accepted))
        self.assertTrue(self.reactor.want_write())
        self.send_packet(MqttPingreq())

        # Next deadline is idle abort.
        self.assertEqual(self.recv_idle_ping_period, self.scheduler.remaining())
        self.scheduler.poll(self.scheduler.remaining())

        # A pingresp is an error at this point.
        self.reactor.terminate()

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

    def test_connected_keepalive_with_recv_qos0(self):
        self.start_to_connected()

        # Time passes; receives QoS=0
        # This resets the recv_idle_*_period timers but does not reset
        # the keepalive timer.
        time_until_publish = self.keepalive_period//2 + 1
        self.poll(time_until_publish)
        pub0 = MqttPublish(18511, u'/test/MT2007/konyha', b'', dupe=False, qos=0, retain=False)
        self.recv_packet_then_ewouldblock(pub0)

        # Expire the keepalive timer; verify pingreq is sent.
        time_until_keepalive = self.keepalive_period - time_until_publish
        self.assertEqual(time_until_keepalive, self.scheduler.remaining())
        self.assertFalse(self.reactor.want_write())
        self.scheduler.poll(time_until_keepalive)
        self.assertTrue(self.reactor.want_write())
        self.send_packet(MqttPingreq())
        self.assertFalse(self.reactor.want_write())

        # Verify that read-path does not generate a new ping while one
        # is already active.
        time_until_recv_idle_ping = time_until_publish + self.recv_idle_ping_period - self.keepalive_period
        self.assertEqual(time_until_recv_idle_ping, self.scheduler.remaining())
        self.scheduler.poll(time_until_recv_idle_ping)
        self.assertFalse(self.reactor.want_write())

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


class TestKeepaliveScheduling16(TestReactor, unittest.TestCase):
    def reactor_properties(self):
        self.keepalive_period = 15  # Set keepalive period so that it dominates.
        self.recv_idle_ping_period = 0  # Disable receive pings.
        self.recv_idle_abort_period = 17
        return TestReactor.reactor_properties(self)

    def test_keepalive_not_scheduled_while_pingreq_active(self):
        """
        https://github.com/kcallin/haka-mqtt/issues/16
        """
        self.start_to_connected()
        self.assertEqual(self.keepalive_period, self.scheduler.remaining())
        self.assertFalse(self.reactor.want_write())
        self.scheduler.poll(self.keepalive_period)
        self.assertTrue(self.reactor.want_write())
        self.send_packet(MqttPingreq())
        self.assertFalse(self.reactor.want_write())

        pub_ticket = self.reactor.publish('topic', b'payload', 1)
        self.assertTrue(self.reactor.want_write())
        self.send_packet(pub_ticket.packet())
        self.assertFalse(self.reactor.want_write())

        recv_idle_abort_remaining = self.recv_idle_abort_period - self.keepalive_period
        self.assertEqual(recv_idle_abort_remaining, self.scheduler.remaining())
        self.scheduler.poll(recv_idle_abort_remaining)

        self.assertEqual(ReactorState.error, self.reactor.state)


class TestKeepaliveDisabled(TestReactor, unittest.TestCase):
    def reactor_properties(self):
        # Set recv_idle_*_period to huge numbers so that keepalive would
        # probably show up if it wasn't disabled.
        self.recv_idle_ping_period = 1000000000
        self.recv_idle_abort_period = 1000000001
        self.keepalive_period = 0
        return TestReactor.reactor_properties(self)

    def test_connack(self):
        # Start with async connect
        self.assertEqual(0, self.reactor.keepalive_period)
        self.start_to_connack()

        self.assertEqual(self.recv_idle_abort_period, self.scheduler.remaining())
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(MqttState.connack, self.reactor.mqtt_state)
        self.assertFalse(self.reactor.want_write())

        # Before a connack is received no pingreq should be sent.
        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertTrue(isinstance(self.reactor.error, RecvTimeoutReactorError), self.reactor.error)
        self.socket.send.assert_not_called()

    def test_connected(self):
        self.start_to_connected()

        self.assertEqual(self.reactor.recv_idle_ping_period, self.scheduler.remaining())
        # Both recv_idle_ping_period and recv_abort_ping_period elapse.
        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertTrue(isinstance(self.reactor.error, RecvTimeoutReactorError), self.reactor.error)
        self.socket.send.assert_not_called()


class TestRecvIdleTimeout(TestReactor, unittest.TestCase):
    def reactor_properties(self):
        self.recv_idle_ping_period = 10
        self.recv_idle_abort_period = 17
        self.keepalive_period = 0  # Disable send path keepalive
        return TestReactor.reactor_properties(self)

    def test_handshake(self):
        # Start with async connect
        self.start_to_handshake()

        self.assertEqual(self.recv_idle_abort_period, self.scheduler.remaining())
        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, RecvTimeoutReactorError))

    def test_connack(self):
        # Start with async connect
        self.start_to_connack()

        self.assertEqual(self.recv_idle_abort_period, self.scheduler.remaining())
        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, RecvTimeoutReactorError))

    def test_connected(self):
        self.start_to_connected()

        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, RecvTimeoutReactorError))

    def test_started_pingreq(self):
        self.start_to_connected()

        min_time_step = 0.00001

        # Test pingreq after connack
        self.assertEqual(self.reactor.recv_idle_ping_period, self.scheduler.remaining())
        self.scheduler.poll(self.reactor.recv_idle_ping_period - min_time_step)
        self.assertFalse(self.reactor.want_write())
        self.scheduler.poll(min_time_step)
        self.assertTrue(self.reactor.want_write())

        self.send_packet(MqttPingreq())
        self.assertFalse(self.reactor.want_write())

        # No incoming packets; idle abort timeout reached.
        time_until_abort = self.reactor.recv_idle_abort_period - self.reactor.recv_idle_ping_period
        self.scheduler.poll(time_until_abort - min_time_step)
        self.assertFalse(self.reactor.want_write())
        self.scheduler.poll(min_time_step)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, RecvTimeoutReactorError))

    def test_started_pingreq_pingresp_pingreq_abort(self):
        self.start_to_connected()

        min_time_step = 0.00001

        # Test pingreq after connack
        self.assertEqual(self.reactor.recv_idle_ping_period, self.scheduler.remaining())
        self.scheduler.poll(self.reactor.recv_idle_ping_period - min_time_step)
        self.assertFalse(self.reactor.want_write())
        self.scheduler.poll(min_time_step)
        self.assertTrue(self.reactor.want_write())

        self.send_packet(MqttPingreq())
        self.assertFalse(self.reactor.want_write())

        # A pingresp arrives just before the abort timeout.
        time_until_abort = self.reactor.recv_idle_abort_period - self.reactor.recv_idle_ping_period
        self.scheduler.poll(time_until_abort - min_time_step)
        self.assertFalse(self.reactor.want_write())
        self.recv_packet_then_ewouldblock(MqttPingresp())
        self.assertEqual(self.recv_idle_ping_period, self.scheduler.remaining())

        # Time passes without receiving any packets; pingreq sent out.
        self.assertEqual(self.reactor.recv_idle_ping_period, self.scheduler.remaining())
        self.scheduler.poll(self.reactor.recv_idle_ping_period - min_time_step)
        self.assertFalse(self.reactor.want_write())
        self.scheduler.poll(min_time_step)
        self.assertTrue(self.reactor.want_write())

        self.send_packet(MqttPingreq())
        self.assertFalse(self.reactor.want_write())

        # No pingresp is received and abort timeout results.
        self.assertAlmostEqual(time_until_abort, self.scheduler.remaining(), delta=min_time_step)
        self.scheduler.poll(time_until_abort)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, RecvTimeoutReactorError))

    def test_mute(self):
        self.start_to_connected()
        self.reactor.stop()

        disconnect = MqttDisconnect()
        self.send_packet(disconnect)

        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, RecvTimeoutReactorError))
