from enum import IntEnum

from haka_mqtt.mqtt import MqttControlPacketType


class MqttRequest(object):
    def __init__(self, packet_type):
        """

        Parameters
        ----------
        packet_type: MqttControlPacketType
        """
        self.__packet_id = None
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
        self._set_packet_id = packet_id

    @property
    def packet_type(self):
        return self.__packet_type


class MqttPublishStatus(IntEnum):
    preflight = 0
    puback = 1
    pubrec = 2
    pubcomp = 3
    done = 4


class MqttPublishRequest(MqttRequest):
    def __init__(self, topic, payload, dupe, qos, retain):
        """

        Parameters
        ----------
        topic: str
        payload: bytes
        dupe: bool
        qos: int
            0 <= qos <= 2
        retain: bool
        """
        super(MqttPublishRequest, self).__init__(MqttControlPacketType.publish)

        assert 0 <= qos <= 2
        assert isinstance(dupe, bool)
        assert isinstance(retain, bool)
        if qos == 0:
            # The DUP flag MUST be set to 0 for all QoS 0 messages
            # [MQTT-3.3.1-2]
            assert dupe is False

        self.topic = topic
        self.payload = payload
        self.dupe = dupe
        self.qos = qos
        self.retain = retain

        self.__status = None

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
        self.__status = None

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
        self.__status = None

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


