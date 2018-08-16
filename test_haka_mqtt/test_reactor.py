from __future__ import print_function

import errno
import logging
import struct
import sys
import unittest
import socket
from io import BytesIO
from select import select
from struct import Struct
from unittest import skip

from mock import Mock

from haka_mqtt.mqtt import MqttConnack, MqttTopic, MqttSuback, SubscribeResult
from haka_mqtt.reactor import (
    Reactor,
    ReactorProperties,
    ReactorState)


def recv_into(packet, buf):
    bio = BytesIO()
    packet.encode(bio)
    src_buf = bio.getvalue()
    buf[0:len(src_buf)] = src_buf
    return len(src_buf)


def write_to_buf(packet):
    bio = BytesIO()
    packet.encode(bio)
    return bio.getvalue()


class TestReactor(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket = Mock()
        self.endpoint = ('test.mosquitto.org', 1883)

        p = ReactorProperties()
        p.socket = self.socket
        p.endpoint = self.endpoint

        self.properties = p
        self.reactor = Reactor(p)

    def tearDown(self):
        pass

    def test_start(self):
        self.assertEqual(ReactorState.init, self.reactor.state)

        self.socket.connect.side_effect = socket.gaierror(errno.EINPROGRESS, '')
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.endpoint)
        self.assertEqual(ReactorState.connecting, self.reactor.state)
        self.assertFalse(self.reactor.want_read())
        self.assertTrue(self.reactor.want_write())

        self.socket.getsockopt.return_value = 0
        self.socket.send.return_value = 19
        self.reactor.write()
        self.assertEqual(self.reactor.state, ReactorState.connack)

        connack = MqttConnack(False, 0)
        self.socket.recv_into.side_effect = lambda buf: recv_into(connack, buf)
        self.socket.recv.return_value = write_to_buf(connack)
        self.reactor.read()
        self.assertEqual(self.reactor.state, ReactorState.connected)

        self.socket.send.return_value = 18
        self.reactor.subscribe([MqttTopic('hello_topic', 0)])

        suback = MqttSuback(0, [SubscribeResult.qos0])
        self.socket.recv_into.side_effect = lambda buf: recv_into(suback, buf)
        self.socket.recv.return_value = write_to_buf(suback)
        self.reactor.read()
        self.assertEqual(self.reactor.state, ReactorState.connected)


class TestIntegrationOfReactor(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setblocking(0)
        self.endpoint = ('test.mosquitto.org', 1883)

        p = ReactorProperties()
        p.socket = self.socket
        p.endpoint = self.endpoint

        self.properties = p
        self.reactor = Reactor(p)

    def tearDown(self):
        self.reactor.terminate()

    @skip('for now.')
    def test_start(self):
        self.reactor.start()
        self.assertEqual(self.reactor.state, ReactorState.connecting)
        i = 0

        while True:
            if self.reactor.want_read():
                rlist = [self.reactor.socket]
            else:
                rlist = []

            if self.reactor.want_write():
                wlist = [self.reactor.socket]
            else:
                wlist = []

            rlist, wlist, xlist = select(rlist, wlist, [])

            for r in rlist:
                assert r == self.reactor.socket
                self.reactor.read()

            for w in wlist:
                assert w == self.reactor.socket
                self.reactor.write()

            # self.assertEqual(self.reactor.state, ReactorState.connecting)
            i += 1
            print(i)


class TestDecode(unittest.TestCase):
    def test_decode(self):
        ba = bytearray('a')
        FIELD_U8 = Struct('>B')
        try:
            b, = FIELD_U8.unpack_from(ba)
        except struct.error as e:
            print(repr(e))

        ba.extend('cdef')