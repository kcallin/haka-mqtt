from enum import IntEnum

from mqtt_codec.packet import MqttControlPacketType, MqttSubscribe, MqttPublish, MqttUnsubscribe


class MqttRequest(object):
    """

    Parameters
    ----------
    packet_id: int
    packet_type: MqttControlPacketType
    """

    def __init__(self, packet_id, packet_type):
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
        """

        Returns
        -------
        MqttControlPacketType
        """
        return self.__packet_type


class MqttPublishStatus(IntEnum):
    preflight = 0
    puback = 1
    pubrec = 2
    pubcomp = 3
    done = 4


class MqttPublishTicket(MqttRequest):
    """

    Parameters
    ----------
    topic: str
    payload: bytes
    qos: int
        0 <= qos <= 2
    retain: bool
    """

    def __init__(self, packet_id, topic, payload, qos, retain=False):
        super(MqttPublishTicket, self).__init__(packet_id, MqttControlPacketType.publish)

        assert 0 <= qos <= 2
        assert isinstance(retain, bool)
        assert isinstance(payload, bytes)

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
        """

        Returns
        -------
        bool
        """
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

    def packet(self):
        return MqttPublish(self.packet_id, self.topic, self.payload, self.dupe, self.qos, self.retain)

    def encode(self, f):
        return self.packet().encode(f)

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
    """

    Parameters
    ----------
    packet_id: int
    topics: iterable of MqttTopic
        Must be one or more topics.
    """

    def __init__(self, packet_id, topics):
        super(MqttSubscribeTicket, self).__init__(packet_id, MqttControlPacketType.subscribe)

        self.__topics = tuple(topics)
        if isinstance(topics, (str, unicode, bytes)):
            raise TypeError()
        assert len(topics) >= 1  # MQTT 3.8.3-3
        self.__status = MqttSubscribeStatus.preflight

    @property
    def topics(self):
        """iterable of MqttTopic: topics subscribed to."""
        return self.__topics

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

    def packet(self):
        return MqttSubscribe(self.packet_id, self.topics)

    def encode(self, f):
        return self.packet().encode(f)

    def __eq__(self, other):
        return (
            hasattr(other, 'topics')
            and self.topics == other.topics
            and hasattr(other, 'status')
            and self.status == other.status
        )


class MqttUnsubscribeTicket(MqttRequest):
    """
    Parameters
    ----------
    packet_id: int
    topics: iterable of str
    """

    def __init__(self, packet_id, topics):
        super(MqttUnsubscribeTicket, self).__init__(packet_id, MqttControlPacketType.unsubscribe)

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
        return self.packet().encode(f)

    def packet(self):
        return MqttUnsubscribe(self.packet_id, self.topics)

    def __eq__(self, other):
        return (
            hasattr(other, 'topics')
            and self.topics == other.topics
            and hasattr(other, 'status')
            and self.status == other.status
        )
