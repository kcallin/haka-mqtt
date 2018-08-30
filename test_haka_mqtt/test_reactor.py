from __future__ import print_function

import errno
import logging
import os
import sys
import unittest
import socket
from io import BytesIO

from mock import Mock

from haka_mqtt.mqtt import (
    MqttConnack,
    MqttTopic,
    MqttSuback,
    SubscribeResult,
    MqttConnect,
    MqttSubscribe,
    MqttPublish,
    MqttPuback,
    MqttPingreq,
    MqttPubrec,
    MqttPubrel,
    MqttPubcomp,
    ConnackResult
)
from haka_mqtt.reactor import (
    Reactor,
    ReactorProperties,
    ReactorState,
    KeepaliveTimeoutReactorError,
    MqttConnectFail, INACTIVE_STATES, SocketError)
from haka_mqtt.scheduler import Scheduler


def buffer_packet(packet):
    bio = BytesIO()
    packet.encode(bio)
    return bio.getvalue()


def socket_error(errno):
    return socket.error(errno, os.strerror(errno))


class TestReactor(unittest.TestCase):
    def reactor_properties(self):
        p = ReactorProperties()
        p.socket_factory = lambda: self.socket
        p.endpoint = self.endpoint
        p.client_id = self.client_id
        p.keepalive_period = self.keepalive_period
        p.scheduler = self.scheduler
        p.clean_session = True

        return p

    def setUp(self):
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
        self.socket = Mock()
        self.endpoint = ('test.mosquitto.org', 1883)
        self.client_id = 'client'
        self.keepalive_period = 10*60
        self.scheduler = Scheduler()

        self.on_publish = Mock()
        self.on_pubrel = Mock()
        self.on_pubrec = Mock()
        self.on_pubcomp = Mock()
        self.on_connack = Mock()
        self.on_puback = Mock()

        self.properties = self.reactor_properties()
        self.reactor = Reactor(self.properties)
        self.reactor.on_publish = self.on_publish
        self.reactor.on_connack = self.on_connack
        self.reactor.on_pubrel = self.on_pubrel
        self.reactor.on_pubcomp = self.on_pubcomp
        self.reactor.on_pubrec = self.on_pubrec
        self.reactor.on_puback = self.on_puback

        self.log = logging.getLogger(self.__class__.__name__)
        self.log.info('%s setUp()', self._testMethodName)

    def tearDown(self):
        self.assertEqual(0, len(self.scheduler))
        self.log.info('%s tearDown()', self._testMethodName)

    def set_recv_side_effect(self, rv_iterable):
        self.socket.recv.side_effect = rv_iterable

    def read_packet_then_block(self, p):
        self.set_recv_side_effect([buffer_packet(p), socket.error(errno.EWOULDBLOCK)])
        self.reactor.read()
        self.socket.recv.assert_called_once()
        self.socket.recv.reset_mock()
        self.socket.recv.side_effect = None
        self.socket.recv.return_value = None

    def set_send_side_effect(self, rv_iterable):
        self.socket.send.side_effect = rv_iterable

    def set_send_packet_side_effect(self, p):
        self.set_send_side_effect([len(buffer_packet(p))])

    def send_packet(self, p):
        buf = buffer_packet(p)
        self.set_send_side_effect([len(buf)])

        self.reactor.write()
        self.socket.send.assert_called_once_with(buf)
        self.socket.send.reset_mock()

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

    def start_to_connect(self):
        self.assertTrue(self.reactor.state in INACTIVE_STATES)

        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.endpoint)
        self.socket.connect.reset_mock()
        self.assertEqual(ReactorState.connecting, self.reactor.state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.send_packet(MqttConnect(self.client_id, self.properties.clean_session, self.keepalive_period))
        self.assertEqual(self.reactor.state, ReactorState.connack)

    def start_to_connack(self):
        self.assertTrue(self.reactor.state in INACTIVE_STATES)

        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.endpoint)
        self.socket.connect.reset_mock()
        self.assertEqual(ReactorState.connecting, self.reactor.state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.send_packet(MqttConnect(self.client_id, self.properties.clean_session, self.keepalive_period))
        self.assertEqual(self.reactor.state, ReactorState.connack)

        connack = MqttConnack(False, ConnackResult.accepted)
        self.read_packet_then_block(connack)
        self.assertEqual(self.reactor.state, ReactorState.connected)


class TestReactorPaths(TestReactor, unittest.TestCase):
    def test_connack_keepalive_timeout(self):
        self.start_to_connect()
        p = MqttPingreq()
        self.set_send_packet_side_effect(p)
        self.scheduler.poll(self.keepalive_period)
        self.socket.send.assert_called_once_with(buffer_packet(p))
        self.socket.send.reset_mock()

        self.scheduler.poll(self.keepalive_period * 0.5)
        self.assertEqual(ReactorState.error, self.reactor.state)
        self.assertEqual(self.reactor.error, KeepaliveTimeoutReactorError())

    def test_connack_unexpected_session_present(self):
        self.start_to_connect()

        connack = MqttConnack(True, ConnackResult.accepted)
        self.read_packet_then_block(connack)
        self.assertEqual(self.reactor.state, ReactorState.error)
        self.on_connack.assert_not_called()

    def test_start(self):
        self.start_to_connack()

        # Subscribe to topic
        topic_name = 'bear_topic'
        p = MqttSubscribe(0, [MqttTopic(topic_name, 0)])
        self.set_send_packet_side_effect(p)
        self.reactor.subscribe(p.topics)
        self.socket.send.assert_called_once_with(buffer_packet(p))
        self.socket.send.reset_mock()

        # Acknowledge subscription to new topic
        suback = MqttSuback(p.packet_id, [SubscribeResult.qos0])
        self.read_packet_then_block(suback)
        self.assertEqual(self.reactor.state, ReactorState.connected)

        # Publish new message
        p = MqttPublish(1, topic_name, 'outgoing', False, 1, False)
        self.set_send_packet_side_effect(p)
        self.reactor.publish(p.topic, p.payload, p.qos)
        self.socket.send.assert_called_once_with(buffer_packet(p))
        self.socket.send.reset_mock()

        # Acknowledge new message
        p = MqttPuback(p.packet_id)
        self.read_packet_then_block(p)
        self.socket.send.assert_not_called()

        publish = MqttPublish(1, topic_name, 'incoming', False, 1, False)
        puback = MqttPuback(p.packet_id)
        self.set_send_packet_side_effect(puback)
        self.read_packet_then_block(publish)
        self.on_publish.assert_called_once_with(self.reactor, publish)
        self.on_publish.reset_mock()
        self.socket.send.assert_called_once_with(buffer_packet(puback))

        self.reactor.terminate()

    def test_conn_and_connack_dripfeed(self):
        self.assertEqual(ReactorState.init, self.reactor.state)

        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.endpoint)
        self.assertEqual(ReactorState.connecting, self.reactor.state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.set_send_packet_drip_and_write(MqttConnect(self.client_id, True, self.keepalive_period))
        self.assertEqual(self.reactor.state, ReactorState.connack)

        connack = MqttConnack(False, ConnackResult.accepted)
        self.read_packet_then_block(connack)
        self.assertEqual(self.reactor.state, ReactorState.connected)

        TOPIC = 'bear_topic'
        p = MqttSubscribe(0, [MqttTopic(TOPIC, 0)])
        self.set_send_packet_side_effect(p)
        self.reactor.subscribe(p.topics)
        self.socket.send.assert_called_once_with(buffer_packet(p))
        self.socket.send.reset_mock()

        suback = MqttSuback(p.packet_id, [SubscribeResult.qos0])
        self.read_packet_then_block(suback)
        self.assertEqual(self.reactor.state, ReactorState.connected)

        p = MqttPublish(1, TOPIC, 'outgoing', False, 1, False)
        self.set_send_packet_side_effect(p)
        self.reactor.publish(p.topic, p.payload, p.qos)
        self.socket.send.assert_called_once_with(buffer_packet(p))
        self.socket.send.reset_mock()

        p = MqttPuback(p.packet_id)
        self.read_packet_then_block(p)

        publish = MqttPublish(1, TOPIC, 'incoming', False, 1, False)
        puback = MqttPuback(p.packet_id)
        self.set_send_packet_side_effect(puback)
        self.read_packet_then_block(publish)
        self.on_publish.assert_called_once_with(self.reactor, publish)
        self.on_publish.reset_mock()
        self.socket.send.assert_called_once_with(buffer_packet(puback))

        self.reactor.terminate()


class TestConnackFail(TestReactor, unittest.TestCase):
    def test_connack_failures(self):
        fail_codes = [r for r in ConnackResult if r != ConnackResult.accepted]
        fail_codes.sort()

        for fail_code in fail_codes:
            self.start_to_connect()

            connack = MqttConnack(False, fail_code)
            self.read_packet_then_block(connack)
            self.assertEqual(self.reactor.state, ReactorState.error)
            self.assertEqual(self.reactor.error, MqttConnectFail(fail_code))


class TestSendPathQos1(TestReactor, unittest.TestCase):
    def reactor_properties(self):
        p = super(type(self), self).reactor_properties()
        p.clean_session = False
        return p

    def start_and_publish_qos1(self):
        self.start_to_connack()

        publish = MqttPublish(0, 'topic', 'outgoing', False, 1, False)
        self.set_send_packet_side_effect(publish)
        actual_publish = self.reactor.publish(publish.topic,
                                       publish.payload,
                                       publish.qos,
                                       publish.retain)
        self.assertFalse(self.reactor.want_write())
        self.assertEqual(publish, actual_publish)
        self.socket.send.reset_mock()

        return publish

    def test_publish_qos1(self):
        publish = self.start_and_publish_qos1()

        puback = MqttPuback(publish.packet_id)
        self.read_packet_then_block(puback)
        self.on_puback.assert_called_once()

        self.reactor.terminate()

    def test_publish_qos1_out_of_order_puback(self):
        self.start_and_publish_qos1()

        publish = MqttPublish(1, 'topic', 'outgoing', False, 1, False)
        self.set_send_packet_side_effect(publish)
        actual_publish = self.reactor.publish(publish.topic,
                                       publish.payload,
                                       publish.qos,
                                       publish.retain)
        self.assertFalse(self.reactor.want_write())
        self.assertEqual(publish, actual_publish)
        self.socket.send.reset_mock()

        puback = MqttPuback(publish.packet_id)
        self.read_packet_then_block(puback)
        self.on_puback.assert_not_called()
        self.assertEqual(self.reactor.state, ReactorState.error)

        self.reactor.terminate()

    def test_publish_qos1_pubrec(self):
        publish = self.start_and_publish_qos1()

        puback = MqttPubrec(publish.packet_id)
        self.read_packet_then_block(puback)
        self.on_puback.assert_not_called()
        self.assertEqual(self.reactor.state, ReactorState.error)

        self.reactor.terminate()

    def test_puback_not_in_flight(self):
        self.start_to_connack()

        puback = MqttPuback(0)
        self.read_packet_then_block(puback)
        self.on_puback.assert_not_called()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_publish_disconnect_connect_republish_qos1(self):
        publish = self.start_and_publish_qos1()

        self.reactor.terminate()

        self.assertEqual(ReactorState.stopped, self.reactor.state)

        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.endpoint)
        self.assertEqual(ReactorState.connecting, self.reactor.state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.send_packet(MqttConnect(self.client_id, self.properties.clean_session, self.keepalive_period))
        self.assertEqual(self.reactor.state, ReactorState.connack)

        connack = MqttConnack(False, ConnackResult.accepted)
        self.set_send_side_effect([len(buffer_packet(publish))])
        self.read_packet_then_block(connack)
        self.set_send_packet_side_effect(publish)
        self.assertEqual(self.reactor.state, ReactorState.connected)
        self.socket.send.assert_called_once_with(buffer_packet(publish))
        self.assertFalse(self.reactor.want_write())

        self.reactor.terminate()


class TestSendPathQos2(TestReactor, unittest.TestCase):
    def reactor_properties(self):
        p = super(type(self), self).reactor_properties()
        p.clean_session = False
        return p

    def start_and_publish_qos2(self):
        self.start_to_connack()

        publish = MqttPublish(0, 'topic', 'outgoing', False, 2, False)
        self.set_send_packet_side_effect(publish)
        actual_publish = self.reactor.publish(publish.topic,
                                       publish.payload,
                                       publish.qos,
                                       publish.retain)
        self.socket.send.reset_mock()
        self.assertFalse(self.reactor.want_write())
        self.assertEqual(publish, actual_publish)

        return publish

    def test_publish_qos2_out_of_order_pubrec(self):
        self.start_and_publish_qos2()

        publish = MqttPublish(1, 'topic', 'outgoing', False, 2, False)
        self.set_send_packet_side_effect(publish)
        actual_publish = self.reactor.publish(publish.topic,
                                       publish.payload,
                                       publish.qos,
                                       publish.retain)
        self.socket.send.reset_mock()
        self.assertFalse(self.reactor.want_write())
        self.assertEqual(publish, actual_publish)

        pubrec = MqttPubrec(publish.packet_id)
        self.read_packet_then_block(pubrec)
        self.on_pubrec.assert_not_called()
        self.socket.send.assert_not_called()
        self.socket.send.reset_mock()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_pubrec_not_in_flight_packet_id(self):
        self.start_to_connack()

        pubrec = MqttPubrec(0)
        self.read_packet_then_block(pubrec)
        self.on_pubrec.assert_not_called()
        self.socket.send.assert_not_called()
        self.socket.send.reset_mock()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_publish_qos2_puback_error(self):
        publish = self.start_and_publish_qos2()

        puback = MqttPuback(publish.packet_id)
        self.read_packet_then_block(puback)
        self.socket.send.assert_not_called()
        self.socket.send.reset_mock()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_publish_disconnect_qos2(self):
        self.start_to_connack()

        publish = MqttPublish(0, 'topic', 'incoming', False, 2, False)
        se = socket_error(errno.ECONNABORTED)
        self.set_send_side_effect([se])
        actual_publish = self.reactor.publish(publish.topic,
                                       publish.payload,
                                       publish.qos,
                                       publish.retain)
        self.assertEqual(publish, actual_publish)
        self.assertEqual(self.reactor.state, ReactorState.error)
        self.assertEqual(self.reactor.error, SocketError(se.errno))
        self.socket.send.reset_mock()

        self.start_to_connect()

        connack = MqttConnack(False, ConnackResult.accepted)
        # TODO: dupe flag should be set.
        self.set_send_packet_side_effect(publish)
        self.read_packet_then_block(connack)
        self.assertEqual(self.reactor.state, ReactorState.connected)
        self.socket.send.assert_called_once_with(buffer_packet(publish))
        self.socket.send.reset_mock()

        pubrec = MqttPubrec(publish.packet_id)
        pubrel = MqttPubrel(publish.packet_id)
        self.set_send_packet_side_effect(pubrel)
        self.read_packet_then_block(pubrec)
        self.on_pubrec.assert_called_once()
        self.socket.send.assert_called_once_with(buffer_packet(pubrel))
        self.socket.send.reset_mock()

        pubcomp = MqttPubcomp(publish.packet_id)
        self.read_packet_then_block(pubcomp)
        self.on_pubcomp.assert_called_once()
        self.socket.send.assert_not_called()

        self.reactor.terminate()

    def test_pubrel_disconnect_qos2(self):
        self.start_to_connack()

        publish = MqttPublish(0, 'topic', 'incoming', False, 2, False)
        self.set_send_packet_side_effect(publish)
        actual_publish = self.reactor.publish(publish.topic,
                                       publish.payload,
                                       publish.qos,
                                       publish.retain)
        self.socket.send.reset_mock()
        self.assertFalse(self.reactor.want_write())
        self.assertEqual(publish, actual_publish)

        pubrec = MqttPubrec(publish.packet_id)
        pubrel = MqttPubrel(publish.packet_id)
        se = socket_error(errno.ECONNABORTED)
        self.set_send_side_effect([se])
        self.read_packet_then_block(pubrec)
        self.on_pubrec.assert_called_once()
        self.socket.send.assert_called_once_with(buffer_packet(pubrel))
        self.socket.send.reset_mock()

        self.assertEqual(self.reactor.state, ReactorState.error)
        self.assertEqual(self.reactor.error, SocketError(se.errno))

        self.start_to_connect()

        connack = MqttConnack(False, ConnackResult.accepted)
        self.set_send_packet_side_effect(pubrel)
        self.read_packet_then_block(connack)
        self.assertEqual(self.reactor.state, ReactorState.connected)
        self.socket.send.assert_called_once_with(buffer_packet(pubrel))
        self.socket.send.reset_mock()

        pubcomp = MqttPubcomp(publish.packet_id)
        self.read_packet_then_block(pubcomp)
        self.on_pubcomp.assert_called_once()
        self.socket.send.assert_not_called()

        self.assertEqual(self.reactor.state, ReactorState.connected)

        self.reactor.terminate()


class TestReceivePathQos1(TestReactor, unittest.TestCase):
    def test_recv_publish(self):
        self.start_to_connack()

        topic_name = 'bear_topic'
        p = MqttSubscribe(0, [MqttTopic(topic_name, 1)])
        self.set_send_packet_side_effect(p)
        self.reactor.subscribe(p.topics)
        self.socket.send.assert_called_once_with(buffer_packet(p))
        self.socket.send.reset_mock()

        suback = MqttSuback(p.packet_id, [SubscribeResult.qos1])
        self.read_packet_then_block(suback)
        self.assertEqual(self.reactor.state, ReactorState.connected)

        self.on_publish.assert_not_called()
        publish = MqttPublish(1, topic_name, 'incoming', False, 1, False)
        self.set_send_side_effect([len(buffer_packet(publish))])
        self.read_packet_then_block(publish)
        self.on_publish.assert_called_once()

        puback = MqttPuback(publish.packet_id)
        self.socket.send.assert_called_once_with(buffer_packet(puback))
        self.socket.send.reset_mock()

        self.reactor.terminate()


class TestReceivePathQos2(TestReactor, unittest.TestCase):
    def test_recv_publish(self):
        self.start_to_connack()

        TOPIC = 'bear_topic'
        p = MqttSubscribe(0, [MqttTopic(TOPIC, 2)])
        self.set_send_packet_side_effect(p)
        self.reactor.subscribe(p.topics)
        self.socket.send.assert_called_once_with(buffer_packet(p))
        self.socket.send.reset_mock()

        suback = MqttSuback(p.packet_id, [SubscribeResult.qos2])
        self.read_packet_then_block(suback)
        self.assertEqual(self.reactor.state, ReactorState.connected)

        self.on_publish.assert_not_called()
        publish = MqttPublish(1, TOPIC, 'outgoing', False, 2, False)
        self.set_send_side_effect([len(buffer_packet(publish))])
        self.read_packet_then_block(publish)
        self.on_publish.assert_called_once()

        pubrec = MqttPubrec(publish.packet_id)
        self.socket.send.assert_called_once_with(buffer_packet(pubrec))
        self.socket.send.reset_mock()

        self.on_pubrel.assert_not_called()
        pubrel = MqttPubrel(publish.packet_id)
        pubcomp = MqttPubcomp(publish.packet_id)
        self.set_send_side_effect([len(buffer_packet(pubcomp))])
        self.read_packet_then_block(pubrel)
        self.assertEqual(ReactorState.connected, self.reactor.state)
        self.on_pubrel.assert_called_once()

        pubcomp = MqttPubcomp(publish.packet_id)
        self.socket.send.assert_called_once_with(buffer_packet(pubcomp))
        self.socket.send.reset_mock()

        self.reactor.terminate()


class TestReactorPeerDisconnect(TestReactor, unittest.TestCase):
    def test_connect(self):
        self.assertEqual(self.reactor.state, ReactorState.init)
        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.endpoint)
        self.assertEqual(ReactorState.connecting, self.reactor.state)
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
        self.socket.connect.assert_called_once_with(self.endpoint)
        self.assertEqual(ReactorState.connecting, self.reactor.state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.send_packet(MqttConnect(self.client_id, True, self.keepalive_period))
        self.assertEqual(self.reactor.state, ReactorState.connack)

        self.set_recv_side_effect([''])
        self.reactor.read()
        self.assertEqual(self.reactor.state, ReactorState.error)

    def test_connected(self):
        self.assertEqual(self.reactor.state, ReactorState.init)
        self.socket.connect.side_effect = socket.error(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.endpoint)
        self.assertEqual(ReactorState.connecting, self.reactor.state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.send_packet(MqttConnect(self.client_id, True, self.keepalive_period))
        self.assertEqual(self.reactor.state, ReactorState.connack)

        self.read_packet_then_block(MqttConnack(False, ConnackResult.accepted))
        self.assertEqual(self.reactor.state, ReactorState.connected)

        self.set_recv_side_effect([''])
        self.reactor.read()
