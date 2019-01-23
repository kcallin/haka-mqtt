import unittest

from haka_mqtt.on_str import HexOnStr


class TestHexOnStr(unittest.TestCase):
    def test_hex_on_str(self):
        buf = b'\n'
        self.assertEqual('0a', str(HexOnStr(buf)))
