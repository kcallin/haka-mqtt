from binascii import b2a_hex


class HexOnStr(object):
    def __init__(self, buf):
        self.__buf = buf
        self.__str = None

    def __str__(self):
        if self.__str is None:
            self.__str = b2a_hex(self.__buf)

        return self.__str


class ReprOnStr(object):
    def __init__(self, o):
        self.__o = o
        self.__repr = None

    def __str__(self):
        if self.__repr is None:
            self.__repr = repr(self.__o)

        return self.__repr
