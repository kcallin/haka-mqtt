import codecs
from io import BytesIO

from enum import IntEnum


class EncodeError(Exception):
    pass


class OverflowEncodeError(Exception):
    pass


class DecodeError(Exception):
    pass


class UnderflowDecodeError(DecodeError):
    pass


class MqttControlPacketType(IntEnum):
    connect = 1
    connack = 2
    publish = 3
    puback = 4
    pubrec = 5
    pubrel = 6
    pubcomp = 7
    subscribe = 8
    suback = 9
    unsubscribe = 10
    unsuback = 11
    pingreq = 12
    pingresp = 13
    disconnect = 14


def are_flags_valid(packet_type, flags):
    """
    [MQTT-2.2.2-1]

    Parameters
    ----------
    packet_type
    flags

    Returns
    -------

    """
    if packet_type == MqttControlPacketType.publish:
        rv = 0 <= flags <= 15
    elif packet_type in (MqttControlPacketType.pubrel,
                         MqttControlPacketType.subscribe,
                         MqttControlPacketType.unsubscribe):
        rv = flags == 2
    elif packet_type in (MqttControlPacketType.connect,
                         MqttControlPacketType.connack,
                         MqttControlPacketType.puback,
                         MqttControlPacketType.pubrec,
                         MqttControlPacketType.pubcomp,
                         MqttControlPacketType.suback,
                         MqttControlPacketType.unsuback,
                         MqttControlPacketType.pingreq,
                         MqttControlPacketType.pingresp,
                         MqttControlPacketType.disconnect):
        rv = flags == 0
    else:
        raise NotImplementedError()

    return rv


def decode_varint(buf):
    """
    line 297

    Parameters
    ----------
    buf

    Returns
    -------

    """
    num_bytes_consumed = 0

    try:
        v = 0
        m = 1

        while True:
            b = buf[num_bytes_consumed]
            v += (b & 0x7f) * m
            m *= 0x80
            num_bytes_consumed += 1

            if b & 0x80 == 0:
                break
            elif num_bytes_consumed >= 4:
                raise DecodeError('Variable integer contained more than 4 bytes.')

        return num_bytes_consumed, v
    except IndexError:
        raise UnderflowDecodeError()


def encode_varint(v, f):
    """

    Parameters
    ----------
    v: int
    f: file
        File-like object

    Returns
    -------
    int
        Number of bytes written.
    """
    num_bytes = 0

    try:
        while True:
            b = v % 0x80
            v = v // 0x80

            if v > 0:
                b = b | 0x80

            f.write(chr(b))

            num_bytes += 1
            if v == 0:
                break

        return num_bytes
    except IndexError:
        raise UnderflowDecodeError()


def decode_utf8(buf):
    try:
        decode = codecs.getdecoder('utf8')

        num_string_bytes = (buf[0] << 8) + buf[1]
        num_bytes_consumed = 2 + num_string_bytes
        s, num_chars = decode(buf[2:num_bytes_consumed])

        return num_bytes_consumed, s
    except IndexError:
        raise UnderflowDecodeError()
    except UnicodeError:
        raise DecodeError('Invalid unicode character.')


def encode_utf8(s, f):
    encode = codecs.getencoder('utf8')

    encoded_str_bytes, num_encoded_chars = encode(s)
    num_encoded_str_bytes = len(encoded_str_bytes)
    assert 0 <= num_encoded_str_bytes <= 2**16-1
    num_encoded_bytes = num_encoded_str_bytes + 2

    f.write(chr((num_encoded_str_bytes & 0xff00) >> 8))
    f.write(chr(num_encoded_str_bytes & 0x00ff))
    f.write(encoded_str_bytes)

    return num_encoded_bytes


def decode_bytes(buf):
    try:
        decode = codecs.getdecoder('utf8')

        num_string_bytes = (ord(buf[0]) << 8) + ord(buf[1])
        num_bytes_consumed = 2 + num_string_bytes
        s, num_chars = decode(buf[2:num_bytes_consumed])

        return num_bytes_consumed, s
    except IndexError:
        raise UnderflowDecodeError()
    except UnicodeError:
        raise DecodeError('Invalid unicode character.')


def encode_bytes(src_buf, dst_buf):
    len_src_buf = len(src_buf)
    assert 0 <= len_src_buf <= 2**16-1
    num_written_bytes = len_src_buf + 2

    if len(dst_buf) < num_written_bytes:
        raise OverflowEncodeError()

    dst_buf[2:num_written_bytes] = src_buf
    dst_buf[0] = (len_src_buf & 0xff00) >> 8
    dst_buf[1] = (len_src_buf & 0x00ff)

    return num_written_bytes


class MqttFixedHeader(object):
    """

    See 2.2 Fixed Header: 233

             7 6 5 4 3 2 1 0
    byte 1  |-------|-------|
              cntrl  flags
    byte 2  | remaining length|
    """
    def __init__(self, packet_type, flags, remaining_len):
        """

        Parameters
        ----------
        packet_type: MqttControlPacketType
        flags: int
        remaining_len: int
        """
        self.packet_type = packet_type

        assert are_flags_valid(packet_type, flags)

        self.flags = flags
        self.remaining_len = remaining_len

    @staticmethod
    def decode(buf):
        """

        Parameters
        ----------
        buf

        Returns
        -------
        (num_bytes_consumed: int, MqttFixedHeader)

        """
        try:
            byte_0 = buf[0]

            packet_type_byte = (byte_0 >> 4)
            flags = byte_0 & 0x0f

            try:
                packet_type = MqttControlPacketType(packet_type_byte)
            except ValueError:
                raise DecodeError('Unknown packet type 0x{:02x}.'.format(packet_type_byte))

            if not are_flags_valid(packet_type, flags):
                raise DecodeError('Invalid flags for packet type.')
        except IndexError:
            raise UnderflowDecodeError()

        num_bytes_consumed = 1
        num_nrb_bytes, num_remaining_bytes = decode_varint(buf[num_bytes_consumed:])
        num_bytes_consumed += num_nrb_bytes

        return num_bytes_consumed, MqttFixedHeader(packet_type, flags, num_remaining_bytes)

    def encode(self, f):
        """

        Parameters
        ----------
        f: file
            file-like object

        Returns
        -------
        int
            Number of bytes written.

        """
        try:
            b = (int(self.packet_type) << 4) | self.flags
            f.write(chr(b))
            num_bytes_consumed = 1
            num_bytes_consumed += encode_varint(self.remaining_len, f)
        except IndexError:
            raise OverflowEncodeError()

        return num_bytes_consumed


class MqttWill(object):
    def __init__(self, qos, topic, message, retain):
        """

        Parameters
        ----------
        qos: int
            0 <= qos <= 2
        topic: str
        message: bytes
        retain: bool
        """
        self.qos = qos
        self.topic = topic
        self.message = message
        self.retain = retain


class MqttPublishHeader(MqttFixedHeader):
    def __init__(self, dupe, retain, will=None):
        """

        Parameters
        ----------
        dup: bool
        retain: bool
        will: MqttWill
        """

        self.dupe = dupe
        self.will = will
        self.retain = retain

        flags = (self.qos << 1)
        if self.dupe:
            flags = flags | 0x04

        if self.retain:
            flags = flags | 0x01

        MqttFixedHeader.__init__(self,
                                 MqttControlPacketType.publish,
                                 flags,
                                 0)


class MqttConnect(MqttFixedHeader):
    CONNECT_HEADER = b'\x00\x04MQTT'
    PROTOCOL_LEVEL = b'\x04'

    def __init__(self, client_id, clean_session, keep_alive, username=None, password=None, will=None):
        """

        Parameters
        ----------
        client_id: str
        clean_session: bool
        keep_alive: int
        username: str or None
        password: str or None
        will: MqttWill
        """
        self.client_id = client_id
        self.username = username
        self.password = password
        self.clean_session = clean_session
        self.keep_alive = keep_alive
        self.will = will

        bio = BytesIO()
        self.encode_body(bio)
        num_body_bytes = len(bio.getvalue())
        MqttFixedHeader.__init__(self, MqttControlPacketType.connect, 0, num_body_bytes)

    @staticmethod
    def __encode_name(f):
        f.write(MqttConnect.CONNECT_HEADER)
        return len(MqttConnect.CONNECT_HEADER)

    @staticmethod
    def __encode_protocol_level(f):
        f.write(MqttConnect.PROTOCOL_LEVEL)

        return 1

    def __encode_connect_flags(self, f):
        flags = 0x00

        if self.username:
            flags = flags | 0x80

        if self.password:
            flags = flags | 0x40

        if self.will is not None:
            flags = flags | 0x04

            if self.will.retain:
                flags = flags | 0x20

            if self.will.qos:
                flags = flags | (self.will.qos << 3)

        if self.clean_session:
            flags = flags | 0x02

        f.write(chr(flags))

        return 1

    def __encode_keep_alive(self, f):
        f.write(chr((self.keep_alive & 0xff00) >> 8))
        f.write(chr(self.keep_alive & 0x00ff))

        return 2

    def encode_body(self, f):
        """

        Parameters
        ----------
        f

        Returns
        -------
        int
            Number of bytes written to file.
        """
        num_bytes_written = 0
        num_bytes_written += self.__encode_name(f)
        num_bytes_written += self.__encode_protocol_level(f)
        num_bytes_written += self.__encode_connect_flags(f)
        num_bytes_written += self.__encode_keep_alive(f)

        if self.client_id is not None:
            num_bytes_written += encode_utf8(self.client_id, f)

        if self.will is not None:
            num_bytes_written += encode_utf8(self.will.topic, f)
            num_bytes_written += encode_bytes(self.will.message, f)

        if self.username is not None:
            num_bytes_written += encode_utf8(self.username, f)

        if self.password is not None:
            num_bytes_written += encode_utf8(self.password, f)

        return num_bytes_written

    def encode(self, f):
        num_bytes_written = 0
        num_bytes_written += MqttFixedHeader.encode(self, f)
        num_bytes_written += self.encode_body(f)

        return num_bytes_written

    @staticmethod
    def decode_body(buf):
        """

        Parameters
        ----------
        buf

        Returns
        -------
        int
            Number of bytes written to file.
        """

        num_bytes_consumed = 0
        l = len(MqttConnect.CONNECT_HEADER)
        if buf[0:l] != MqttConnect.CONNECT_HEADER:
            raise DecodeError()
        buf = buf[l:]
        num_bytes_consumed += l

        protocol_level = chr(buf[0])
        if protocol_level != MqttConnect.PROTOCOL_LEVEL:
            raise DecodeError('Invalid protocol level {}.'.format(protocol_level))
        buf = buf[1:]
        num_bytes_consumed += 1

        flags = buf[0]
        has_username = bool(flags & 0x80)
        has_password = bool(flags & 0x40)
        has_will = bool(flags & 0x04)
        will_retained = bool(flags & 0x20)
        will_qos = (flags & 0x18) >> 3
        clean_session = bool(flags & 0x02)
        zero = flags & 0x01

        if zero != 0:
            raise DecodeError()
        buf = buf[1:]
        num_bytes_consumed += 1

        keep_alive = (buf[0] << 8) + buf[1]
        buf = buf[2:]
        num_bytes_consumed += 2

        num_bytes_consumed, buf, client_id = decode_utf8_buf(num_bytes_consumed, buf)

        if has_will:
            num_bytes_consumed, buf, will_topic = decode_utf8_buf(num_bytes_consumed, buf)
            num_bytes_consumed, buf, will_message = decode_bytes_buf(num_bytes_consumed, buf)
            will = MqttWill(will_qos, will_topic, will_message, will_retained)
        else:
            if will_qos != 0:
                # [MQTT-3.1.2-13]
                raise DecodeError('Expected will_qos to be zero since will flag is zero.')

            will = None

        if has_username:
            num_bytes_consumed, buf, username = decode_utf8_buf(num_bytes_consumed, buf)
        else:
            username = None

        if has_password:
            num_bytes_consumed, buf, password = decode_utf8_buf(num_bytes_consumed, buf)
        else:
            password = None

        connect = MqttConnect(client_id, clean_session, keep_alive, username, password, will)
        return num_bytes_consumed, connect

    @staticmethod
    def decode(buf):
        """

        Parameters
        ----------
        buf

        Returns
        -------
        (num_bytes_consumed: int, MqttFixedHeader)

        """

        num_header_bytes_consumed, hdr = MqttFixedHeader.decode(buf)
        if hdr.packet_type != MqttControlPacketType.connect:
            raise DecodeError('Expected connack packet.')

        num_body_bytes_consumed, connect = MqttConnect.decode_body(buf[num_header_bytes_consumed:])
        if hdr.remaining_len != num_body_bytes_consumed:
            raise DecodeError('Header remaining length not equal to body bytes.')
        num_bytes_consumed = num_header_bytes_consumed + num_body_bytes_consumed

        return num_bytes_consumed, connect


def decode_utf8_buf(num_bytes_consumed, buf):
    """

    Parameters
    ----------
    buf

    Returns
    -------
    (num_bytes_consumed, new_buf, utf8_str)
    """
    num_str_bytes, s = decode_utf8(buf)

    buf = buf[num_str_bytes:]
    num_bytes_consumed += num_str_bytes

    return (num_bytes_consumed, buf, s)


def decode_bytes_buf(num_bytes_consumed, buf):
    """

    Parameters
    ----------
    buf

    Returns
    -------
    (num_bytes_consumed, new_buf, utf8_str)
    """
    num_str_bytes, s = decode_bytes(buf)

    buf = buf[num_str_bytes:]
    num_bytes_consumed += num_str_bytes

    return (num_bytes_consumed, buf, s)


class MqttConnack(MqttFixedHeader):
    def __init__(self, session_present, return_code):
        """

        Parameters
        ----------
        session_present: bool
            Session present.
        return_code: int
            Connack return code [Line 709 mqtt]
        """
        assert 0 <= return_code <= 255

        self.session_present = session_present
        self.return_code = return_code

        bio = BytesIO()
        self.encode_body(bio)
        num_body_bytes = len(bio.getvalue())
        MqttFixedHeader.__init__(self, MqttControlPacketType.connack, 0, num_body_bytes)

    def encode_body(self, f):
        """

        Parameters
        ----------
        f

        Returns
        -------
        int
            Number of bytes written to file.
        """
        num_bytes_written = 2

        if self.session_present:
            flags = 1
        else:
            flags = 0

        f.write(chr(flags))
        f.write(chr(self.return_code))

        return num_bytes_written

    def encode(self, f):
        num_bytes_written = 0
        num_bytes_written += MqttFixedHeader.encode(self, f)
        num_bytes_written += self.encode_body(f)

        return num_bytes_written

        return 1

    @staticmethod
    def decode_body(buf):
        num_bytes_consumed = 2
        if len(buf) < num_bytes_consumed:
            raise UnderflowDecodeError()

        if buf[0] == 0:
            session_present = 0
        elif buf[0] == 1:
            session_present = 1
        else:
            raise DecodeError('Incorrectly encoded session_present flag.')

        return_code = buf[1]
        # 0 - conn accepted
        # 1 - conn refused, unnacceptable protocol version
        # 2 - conn refused, identifier rejected
        # 3 - conn refused server unavailable
        # 4 - conn refused bad user name or password
        # 5 - conn refused not authorized.
        if 0 <= return_code <= 5:
            return num_bytes_consumed, MqttConnack(session_present, return_code)
        else:
            raise DecodeError("Unrecognized return code.")

    @staticmethod
    def decode(buf):
        """

        Parameters
        ----------
        buf

        Returns
        -------
        (num_bytes_consumed: int, MqttFixedHeader)

        """

        num_header_bytes_consumed, hdr = MqttFixedHeader.decode(buf)
        if hdr.packet_type != MqttControlPacketType.connack:
            raise DecodeError('Expected connack packet.')

        num_body_bytes_consumed, connack = MqttConnack.decode_body(buf[num_header_bytes_consumed:])
        num_bytes_consumed = num_header_bytes_consumed + num_body_bytes_consumed

        return num_bytes_consumed, connack

    def __repr__(self):
        msg = 'MqttConnack(session_present=%s, return_code=%s)'
        return msg.format(self.session_present, self.return_code)

