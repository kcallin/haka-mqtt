import unittest

from haka_mqtt.reactor import ReactorState, MqttState, ProtocolReactorError, SocketState, KeepaliveTimeoutReactorError
from mqtt_codec.packet import MqttPingresp, MqttPingreq, MqttDisconnect, MqttTopic, MqttPublish
from tests.reactor_harness import TestReactor


class TestKeepalive(TestReactor, unittest.TestCase):
    def test_connack(self):
        # Start with async connect
        self.start_to_connack()

        # Verify waiting for connack and no writes are needed
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(MqttState.connack, self.reactor.mqtt_state)
        self.assertFalse(self.reactor.want_write())

        # Before a connack is received no pingreq should be sent.
        self.scheduler.poll(self.reactor.keepalive_period - 1)
        self.assertFalse(self.reactor.want_write())
        self.scheduler.poll(1)
        self.assertTrue(self.reactor.want_write())

        # A pingresp is an error at this point.
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


class TestKeepaliveX(TestReactor, unittest.TestCase):
    def reactor_properties(self):
        rp = super(type(self), self).reactor_properties()
        kp = 30
        rp.keepalive_period = kp
        rp.recv_idle_ping_period = kp
        rp.recv_idle_abort_period = int(1.5*kp)

        self.keepalive_period = rp.keepalive_period
        self.recv_idle_ping_period = rp.recv_idle_ping_period
        self.recv_idle_abort_period = rp.recv_idle_abort_period
        return rp

    def test_1(self):
        """
/home/kcallin/src/haka-mqtt/venv/bin/python /home/kcallin/src/haka-mqtt/examples/mqtt-sub.py --keepalive=30 --topic0=Advantech/# --topic0=/test/# --topic0=/temp/# test.mosquitto.org 8883
2018-11-12 08:35:00,333 Starting.
2018-11-12 08:35:00,333 Looking up host test.mosquitto.org:8883.
2018-11-12 08:35:00,426 Found family=inet sock=sock_stream proto=tcp addr=37.187.106.16:8883 (chosen)
2018-11-12 08:35:00,426 Found family=inet6 sock=sock_stream proto=tcp addr=2001:41d0:a:3a10::1:8883
2018-11-12 08:35:00,428 Connecting.
2018-11-12 08:35:00,563 Connected.
2018-11-12 08:35:00,853 Launching message MqttConnect(client_id='client-2018-11-12T08:35:00-grizzly-15509', clean_session=True, keep_alive=30s, username=***, password=***, will=None).
2018-11-12 08:35:00,990 Received MqttConnack(session_present=False, return_code=<ConnackResult.accepted: 0>).
2018-11-12 08:35:00,990 Launching message MqttSubscribe(packet_id=0, topics=[Topic('Advantech/#', max_qos=0), Topic('/test/#', max_qos=0), Topic('/temp/#', max_qos=0)]).
2018-11-12 08:35:01,127 Received MqttSuback(packet_id=0, results=[<SubscribeResult.qos0: 0>, <SubscribeResult.qos0: 0>, <SubscribeResult.qos0: 0>]).
2018-11-12 08:35:01,302 Received MqttPublish(packet_id=31522, topic=u'Advantech/00D0C9FAC3EA/data', payload=0x73223a312c2274223a302c2271223a3139322c2263223a312c22646931223a747275652c22646932223a66616c73652c22646933223a66616c73652c22646934223a66616c73652c22646f31223a66616c73652c22646f32223a66616c73652c22646f33223a66616c73652c22646f34223a66616c73657d, dupe=False, qos=0, retain=True).
2018-11-12 08:35:01,302 Received MqttPublish(packet_id=31522, topic=u'Advantech/00D0C9FAC3EA/Device_Status', payload=0x737461747573223a22636f6e6e656374222c226e616d65223a224144414d36323636222c226d61636964223a22303044304339464143334541222c22697061646472223a2231302e312e312e3133227d, dupe=False, qos=0, retain=True).
2018-11-12 08:35:01,303 Received MqttPublish(packet_id=17513, topic=u'Advantech/Device_Status', payload=0x73636f6e6e656374696f6e5f4144414d363236365f303044304339464541304533, dupe=False, qos=0, retain=True).
2018-11-12 08:35:01,303 Received MqttPublish(packet_id=31522, topic=u'Advantech/00D0C9F8CE88/Device_Status', payload=0x737461747573223a22636f6e6e656374222c226e616d65223a22574953452d343031302f4c414e222c226d61636964223a22303044304339463843453838222c22697061646472223a223139322e3136382e302e313331227d, dupe=False, qos=0, retain=True).
2018-11-12 08:35:01,303 Received MqttPublish(packet_id=12336, topic=u'/test/tfl/bddjpv', payload=0x30303030, dupe=False, qos=0, retain=True).
2018-11-12 08:35:01,303 Received MqttPublish(packet_id=29797, topic=u'/test/publish', payload=0x73742031, dupe=False, qos=0, retain=True).
2018-11-12 08:35:01,304 Received MqttPublish(packet_id=31522, topic=u'/test/iot/srdat', payload=0x747a6f6e65223a20302c202273756e72697365223a2022373a3133222c202273756e736574223a2022343a3135222c202274656d70223a2031322c202268696768223a2031332c20226c6f77223a2031307d, dupe=False, qos=0, retain=True).
2018-11-12 08:35:01,304 Received MqttPublish(packet_id=12851, topic=u'/temp/random', payload=0x, dupe=False, qos=0, retain=True).
2018-11-12 08:35:02,233 Received MqttPublish(packet_id=18511, topic=u'/test/MT2007/konyha', payload=0x3a3234362d50413a343138, dupe=False, qos=0, retain=False).
2018-11-12 08:35:12,274 Received MqttPublish(packet_id=18511, topic=u'/test/MT2007/konyha', payload=0x3a3234342d50413a343137, dupe=False, qos=0, retain=False).
2018-11-12 08:35:22,308 Received MqttPublish(packet_id=18511, topic=u'/test/MT2007/konyha', payload=0x3a3234362d50413a343138, dupe=False, qos=0, retain=False).
2018-11-12 08:35:30,991 Launching message MqttPingreq().
2018-11-12 08:35:31,128 Received MqttPingresp().
2018-11-12 08:35:32,223 Received MqttPublish(packet_id=18511, topic=u'/test/MT2007/konyha', payload=0x3a3234372d50413a343139, dupe=False, qos=0, retain=False).
2018-11-12 08:35:42,253 Received MqttPublish(packet_id=18511, topic=u'/test/MT2007/konyha', payload=0x3a3234372d50413a343139, dupe=False, qos=0, retain=False).
2018-11-12 08:35:52,340 Received MqttPublish(packet_id=18511, topic=u'/test/MT2007/konyha', payload=0x3a3234372d50413a343139, dupe=False, qos=0, retain=False).
2018-11-12 08:36:02,234 Received MqttPublish(packet_id=18511, topic=u'/test/MT2007/konyha', payload=0x3a3234362d50413a343138, dupe=False, qos=0, retain=False).
2018-11-12 08:36:12,241 Received MqttPublish(packet_id=18511, topic=u'/test/MT2007/konyha', payload=0x3a3234342d50413a343137, dupe=False, qos=0, retain=False).
2018-11-12 08:36:16,346 Remote has unexpectedly closed remote->local writes; Aborting.
"""
        self.start_to_connected()
        topics = [MqttTopic('Advantech/#', max_qos=0), MqttTopic('/test/#', max_qos=0), MqttTopic('/temp/#', max_qos=0)]
        self.subscribe_and_suback(topics)

        time_of_next_send_ping = self.clock.time() + self.keepalive_period
        time_of_next_recv_ping = self.clock.time() + self.recv_idle_ping_period
        self.poll(15)
        self.recv_packet_then_ewouldblock(MqttPublish(18511, u'/test/MT2007/konyha', '', dupe=False, qos=0, retain=False))
        time_of_next_recv_ping = self.clock.time() + self.recv_idle_ping_period
        self.poll(time_of_next_send_ping - self.clock.time() - 1)
        self.assertFalse(self.reactor.want_write())

        # First ping (send path)
        self.poll(1)
        self.assertTrue(self.reactor.want_write())
        self.send_packet(MqttPingreq())
        time_of_next_send_ping = self.clock.time() + self.keepalive_period
        self.poll(15)
        self.recv_packet_then_ewouldblock(MqttPingresp())
        time_of_next_recv_ping = self.clock.time() + self.recv_idle_ping_period
        self.poll(time_of_next_send_ping - self.clock.time() - 1)
        self.assertFalse(self.reactor.want_write())

        # Second ping (send path)
        self.poll(1)
        self.assertTrue(self.reactor.want_write())
        self.send_packet(MqttPingreq())
        time_of_next_send_ping = self.clock.time() + self.keepalive_period
        self.poll(5)
        self.recv_packet_then_ewouldblock(MqttPingresp())
        time_of_next_recv_ping = self.clock.time() + self.recv_idle_ping_period
        self.poll(time_of_next_send_ping - self.clock.time() - 1)
        self.assertFalse(self.reactor.want_write())

        # Third ping (send path)
        self.poll(1)
        self.assertTrue(self.reactor.want_write())
        self.send_packet(MqttPingreq())
        time_of_next_send_ping = self.clock.time() + self.keepalive_period
        self.poll(5)
        self.recv_packet_then_ewouldblock(MqttPingresp())
        time_of_next_recv_ping = self.clock.time() + self.recv_idle_ping_period
        self.poll(time_of_next_send_ping - self.clock.time() - 1)
        self.assertFalse(self.reactor.want_write())

        pub = MqttPublish(1, 'topic', 'payload', False, 0, False)
        self.reactor.publish(pub.topic, pub.payload, pub.qos, pub.retain)
        self.assertTrue(self.reactor.want_write())
        self.send_packet(pub)
        time_of_next_send_ping = self.clock.time() + self.keepalive_period
        self.poll(time_of_next_recv_ping - self.clock.time() - 1)
        self.assertFalse(self.reactor.want_write())

        # Fourth ping (recv path)
        self.poll(1)
        self.assertTrue(self.reactor.want_write())
        self.send_packet(MqttPingreq())
        time_of_next_send_ping = self.clock.time() + self.keepalive_period

        self.reactor.terminate()


class TestKeepaliveTimeout(TestReactor, unittest.TestCase):
    def test_handshake(self):
        # Start with async connect
        self.start_to_handshake()

        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, KeepaliveTimeoutReactorError))

    def test_connack(self):
        # Start with async connect
        self.start_to_connack()

        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, KeepaliveTimeoutReactorError))

    def test_connected(self):
        self.start_to_connected()

        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, KeepaliveTimeoutReactorError))

    def test_mute(self):
        self.start_to_connected()
        self.reactor.stop()

        disconnect = MqttDisconnect()
        self.send_packet(disconnect)

        self.assertEqual(SocketState.mute, self.reactor.sock_state)
        self.assertEqual(ReactorState.stopping, self.reactor.state)

        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertTrue(isinstance(self.reactor.error, KeepaliveTimeoutReactorError))


class TestKeepaliveDisabled(TestReactor, unittest.TestCase):
    def reactor_properties(self):
        self.keepalive_period = 0
        return TestReactor.reactor_properties(self)

    def test_connack(self):
        # Start with async connect
        self.assertEqual(0, self.reactor.keepalive_period)
        self.start_to_connack()

        self.assertEqual(1, len(self.scheduler))
        self.assertEqual(ReactorState.starting, self.reactor.state)
        self.assertEqual(MqttState.connack, self.reactor.mqtt_state)
        self.assertFalse(self.reactor.want_write())

        # Before a connack is received no pingreq should be sent.
        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertTrue(isinstance(self.reactor.error, KeepaliveTimeoutReactorError), self.reactor.error)
        self.socket.send.assert_not_called()

    def test_connected(self):
        self.start_to_connected()

        self.assertEqual(1, len(self.scheduler))
        self.scheduler.poll(self.reactor.recv_idle_abort_period)
        self.assertTrue(isinstance(self.reactor.error, KeepaliveTimeoutReactorError), self.reactor.error)
        self.socket.send.assert_not_called()