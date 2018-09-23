from enum import IntEnum

from haka_mqtt.mqtt import MqttControlPacketType, MqttPublish, MqttSubscribe, MqttUnsubscribe


class MqttRequest(object):
    def __init__(self, packet_id, packet_type):
        """

        Parameters
        ----------
        packet_id: int
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
    def __init__(self, packet_id, topic, payload, qos, retain=False):
        """

        Parameters
        ----------
        topic: str
        payload: bytes
        qos: int
            0 <= qos <= 2
        retain: bool
        """
        super(MqttPublishTicket, self).__init__(packet_id, MqttControlPacketType.publish)

        assert 0 <= qos <= 2
        assert isinstance(retain, bool)

        self.topic = topic
        self.payload = payload
        self.qos = qos
        self.retain = retain
        self.__dupe = False

        if qos == 0:
            # The DUP flag MUST be set to 0 for all QoS 0 messages
            # [MQTT-3.3.1-2]
            assert self.dupe is False

        self.__status = MqttPublishStatus.preflight

    @property
    def dupe(self):
        return self.__dupe

    def _set_dupe(self):
        self.__dupe = True


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

    def encode(self, f):
        p = MqttPublish(self.packet_id, self.topic, self.payload, self.dupe, self.qos, self.retain)
        return p.encode(f)

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


class MqttSubscribeTicket(MqttRequest):
    def __init__(self, packet_id, topics):
        """

        Parameters
        ----------
        packet_id: int
        topics: iterable of MqttTopic
            Must be one or more topics.
        """
        super(MqttSubscribeTicket, self).__init__(packet_id, MqttControlPacketType.subscribe)

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

    def encode(self, f):
        p = MqttSubscribe(self.packet_id, self.topics)
        return p.encode(f)


class MqttUnsubscribeRequest(MqttRequest):
    def __init__(self, packet_id, topics):
        """
        Parameters
        ----------
        packet_id: int
        topics: iterable of str
        """
        super(MqttUnsubscribeRequest, self).__init__(packet_id, MqttControlPacketType.unsubscribe)

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

    def encode(self, f):
        p = MqttUnsubscribe(self.packet_id, self.topics)
        return p.encode(f)
