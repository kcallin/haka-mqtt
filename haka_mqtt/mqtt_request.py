from enum import IntEnum

from haka_mqtt.mqtt import MqttControlPacketType, MqttPublish, MqttSubscribe, MqttUnsubscribe


class MqttRequest(object):
    def __init__(self, packet_type, packet_id=None):
        """

        Parameters
        ----------
        packet_type: MqttControlPacketType
        """
        self.__packet_id = packet_id
        self.__packet_type = packet_type

    @property
    def packet_id(self):
        """

        Returns
        -------
        int
            0 <= self.packet_id <= 2**16 - 1
        """
        return self.__packet_id

    def _set_packet_id(self, packet_id):
        """

        Parameters
        ----------
        packet_id: int or None
            0 <= packet_id <= 2**16 -1
        """
        assert packet_id is None or 0 <= packet_id <= 2**16-1
        self.__packet_id = packet_id

    @property
    def packet_type(self):
        return self.__packet_type


class MqttPublishStatus(IntEnum):
    preflight = 0
    puback = 1
    pubrec = 2
    pubcomp = 3
    done = 4


class MqttPublishTicket(MqttRequest):
    def __init__(self, topic, payload, qos, retain, packet_id=None):
        """

        Parameters
        ----------
        topic: str
        payload: bytes
        qos: int
            0 <= qos <= 2
        retain: bool
        """
        super(MqttPublishTicket, self).__init__(MqttControlPacketType.publish, packet_id)

        assert 0 <= qos <= 2
        assert isinstance(retain, bool)

        self.topic = topic
        self.payload = payload
        self.dupe = False
        self.qos = qos
        self.retain = retain

        if qos == 0:
            # The DUP flag MUST be set to 0 for all QoS 0 messages
            # [MQTT-3.3.1-2]
            assert self.dupe is False

        self.__status = MqttPublishStatus.preflight

    def _set_status(self, s):
        """
        Parameters
        ----------
        s: MqttPublishStatus
        """
        self.__status = s

    @property
    def status(self):
        """

        qos = 0

        preflight -> done

        qos = 1
        preflight -> puback -> done

        qos = 2
        preflight -> pubrel -> pubcomp -> done

        Returns
        -------
        MqttPublishStatus
        """
        return self.__status

    def packetize(self, packet_id_iter):
        """

        Parameters
        ----------
        packet_id_iter: iterable of int or None

        Returns
        -------
        MqttPublish
        """
        if self.packet_id is None:
            packet_id = next(packet_id_iter)
        else:
            packet_id = self.packet_id

        return MqttPublish(packet_id, self.topic, self.payload, self.dupe, self.qos, self.retain)

    def __eq__(self, other):
        return (
            hasattr(other, 'topic')
            and self.topic == other.topic
            and hasattr(other, 'packet_id')
            and self.packet_id == other.packet_id
            and hasattr(other, 'packet_type')
            and self.packet_type == other.packet_type
            and hasattr(other, 'packet_type')
            and self.payload == other.payload
            and hasattr(other, 'payload')
            and self.dupe == other.dupe
            and hasattr(other, 'dupe')
            and self.qos == other.qos
            and hasattr(other, 'retain')
            and self.retain == other.retain
        )

    def __repr__(self):
        params = (
            self.__class__.__name__,
            repr(self.status),
            self.packet_id,
            self.topic,
            self.payload,
            self.qos,
            self.dupe,
            self.retain,
        )
        return '{}<self.state={}, packet_id={}, topic={}, payload={}, qos={}, dupe={}, retain={}>'.format(*params)

class MqttSubscribeStatus(IntEnum):
    preflight = 0
    ack = 1
    done = 2


class MqttSubscribeRequest(MqttRequest):
    def __init__(self, topics):
        """

        Parameters
        ----------
        topics: iterable of MqttTopic
        """
        super(MqttSubscribeRequest, self).__init__(MqttControlPacketType.subscribe)

        self.topics = tuple(topics)
        if isinstance(topics, (str, unicode, bytes)):
            raise TypeError()
        assert len(topics) >= 1  # MQTT 3.8.3-3
        self.__status = MqttSubscribeStatus.preflight

    def _set_status(self, s):
        """
        Parameters
        ----------
        s: MqttPublishStatus
        """
        self.__status = s

    @property
    def status(self):
        """
        preflight -> ack -> done

        Returns
        -------
        MqttSubscribeStatus
        """
        return self.__status

    def packetize(self, packet_id_iter):
        """

        Parameters
        ----------
        packet_id_iter: iterable of int or None

        Returns
        -------
        MqttPublish
        """
        if self.packet_id is None:
            packet_id = next(packet_id_iter)
        else:
            packet_id = self.packet_id

        return MqttSubscribe(packet_id, self.topics)


class MqttUnsubscribeRequest(MqttRequest):
    def __init__(self, topics):
        """
        Parameters
        ----------
        topics: iterable of str
        """
        super(MqttUnsubscribeRequest, self).__init__(MqttControlPacketType.unsubscribe)

        self.topics = tuple(topics)

        if isinstance(topics, (str, unicode, bytes)):
            raise TypeError()

        assert len(topics) >= 1  # MQTT 3.10.3-2
        self.__status = MqttSubscribeStatus.preflight

    def _set_status(self, s):
        """
        Parameters
        ----------
        s: MqttPublishStatus
        """
        self.__status = s

    @property
    def status(self):
        """
        preflight -> ack -> done

        Returns
        -------
        MqttSubscribeStatus
        """
        return self.__status

    def packetize(self, packet_id_iter):
        """

        Parameters
        ----------
        packet_id_iter: iterable of int or None

        Returns
        -------
        MqttPublish
        """
        if self.packet_id is None:
            packet_id = next(packet_id_iter)
        else:
            packet_id = self.packet_id

        return MqttUnsubscribe(packet_id, self.topics)


