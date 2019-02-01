import unittest

from haka_mqtt.exception import PacketIdReactorException
from haka_mqtt.packet_ids import PacketIdGenerator


class TestPacketIdGenerator(unittest.TestCase):
    def test_gen(self):
        # Acquire an id and release
        gen = PacketIdGenerator()
        self.assertEqual(0, len(gen))
        self.assertEqual([], list(gen))
        self.assertEqual(1, gen.acquire())
        self.assertEqual(1, len(gen))
        self.assertEqual([1], list(gen))
        gen.release(1)
        self.assertEqual(0, len(gen))
        self.assertEqual([], list(gen))

        # Acquire two ids and release
        self.assertEqual(2, gen.acquire())
        self.assertEqual(1, len(gen))
        self.assertEqual([2], list(gen))
        self.assertEqual(3, gen.acquire())
        self.assertEqual(2, len(gen))
        self.assertEqual([2, 3], list(gen))
        gen.release(2)
        gen.release(3)
        self.assertEqual(0, len(gen))
        self.assertEqual([], list(gen))

    def test_exhaustion(self):
        gen = PacketIdGenerator()
        expected_ids = list(range(1, 2**16))
        for i in expected_ids:
            self.assertEqual(i, gen.acquire())
            self.assertEqual(i, len(gen))

        self.assertEqual(expected_ids, list(gen))
        self.assertRaises(PacketIdReactorException, gen.acquire)
        for i in reversed(expected_ids):
            self.assertEqual(i, len(gen))
            gen.release(i)
            self.assertEqual(i-1, len(gen))

