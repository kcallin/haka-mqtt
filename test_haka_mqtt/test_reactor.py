from __future__ import print_function

import logging
import sys
import unittest
import socket
from select import select

from mock import Mock

from haka_mqtt.reactor import (
    Reactor,
    ReactorProperties,
    ReactorState)


class TestReactor(unittest.TestCase):
    def setUp(self):
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
        self.reactor.start()
        self.socket.connect.assert_called_once_with(self.endpoint)


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
