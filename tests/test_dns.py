from __future__ import print_function
import socket
import unittest

from mock import Mock

from haka_mqtt.dns import AsyncDnsResolver


class TestAsyncDnsResolver(unittest.TestCase):
    def setUp(self):
        pass

    def cb(self, results):
        for family, socktype, proto, canonname, sockaddr in results:
            print(20*'*')
            if family is socket.AF_INET:
                print('family', 'AF_INET')
            elif family is socket.AF_INET6:
                print('family', 'AF_INET6')
            else:
                print('family', family)
            print('socktype', socktype)
            print('proto', proto)
            print('canonname', canonname)
            print('sockaddr', sockaddr)

    def test_resolution(self):
        resolver = AsyncDnsResolver()
        resolver.getaddrinfo(self.cb, "example.org", 80, 0, 0, socket.IPPROTO_TCP)
        resolver.get()


