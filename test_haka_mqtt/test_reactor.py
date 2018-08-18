from __future__ import print_function

import errno
import logging
import struct
import sys
import unittest
import socket
from io import BytesIO
from struct import Struct

from mock import Mock

from haka_mqtt.mqtt import MqttConnack, MqttTopic, MqttSuback, SubscribeResult, MqttConnect, MqttSubscribe
from haka_mqtt.reactor import (
    Reactor,
    ReactorProperties,
    ReactorState)


def buffer_packet(packet):
    bio = BytesIO()
    packet.encode(bio)
    return bio.getvalue()


class TestReactor(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
        self.socket = Mock()
        self.endpoint = ('test.mosquitto.org', 1883)
        self.client_id = 'client'
        self.keepalive_period = 10*60

        p = ReactorProperties()
        p.socket = self.socket
        p.endpoint = self.endpoint
        p.client_id = self.client_id
        p.keepalive_period = self.keepalive_period

        self.properties = p
        self.reactor = Reactor(p)

    def tearDown(self):
        pass

    def set_recv_packet_result(self, p):
        self.socket.recv.return_value = buffer_packet(p)

    def set_recv_packet_result_then_read(self, p):
        self.set_recv_packet_result(p)
        self.reactor.read()
        self.socket.recv.assert_called_once()
        self.socket.recv.reset_mock()

    def set_send_result(self, rv):
        if isinstance(rv, Exception):
            self.socket.send.side_effect = rv
        else:
            self.socket.send.return_value = rv

    def set_send_result_then_write(self, rv, buf):
        self.set_send_result(rv)

        self.reactor.write()
        self.socket.send.assert_called_once_with(buf)
        self.socket.send.reset_mock()

    def set_send_packet_result(self, p, exc=None):
        with BytesIO() as f:
            num_bytes_written = p.encode(f)

        if exc:
            num_bytes_written = exc

        self.set_send_result(num_bytes_written)

    def set_send_packet_result_then_write(self, p, exc=None):
        buf = buffer_packet(p)

        if exc:
            num_bytes_written = exc

        self.set_send_result(len(buf))

        self.reactor.write()
        self.socket.send.assert_called_once_with(buf)
        self.socket.send.reset_mock()

    def encode_packet_to_buf(self, p):
        with BytesIO() as f:
            p.encode(f)
            buf = f.getvalue()

        return bytearray(buf)

    def test_start(self):
        self.assertEqual(ReactorState.init, self.reactor.state)

        self.socket.connect.side_effect = socket.gaierror(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.endpoint)
        self.assertEqual(ReactorState.connecting, self.reactor.state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.set_send_packet_result_then_write(MqttConnect(self.client_id, True, self.keepalive_period))
        self.assertEqual(self.reactor.state, ReactorState.connack)

        connack = MqttConnack(False, 0)
        self.set_recv_packet_result_then_read(connack)
        self.assertEqual(self.reactor.state, ReactorState.connected)

        p = MqttSubscribe(0, [MqttTopic('hello_topic', 0)])
        self.set_send_packet_result(p)
        self.reactor.subscribe(p.topics)
        self.socket.send.assert_called_once_with(buffer_packet(p))

        suback = MqttSuback(0, [SubscribeResult.qos0])
        self.set_recv_packet_result_then_read(suback)
        self.assertEqual(self.reactor.state, ReactorState.connected)
