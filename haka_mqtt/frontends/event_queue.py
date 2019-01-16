from enum import unique, IntEnum


@unique
class MqttConnectionEvent(IntEnum):
    disconnect = 0
    connect_fail = 1


class MqttEventQueue():
    def __init__(self, q):
        self.__q = q

    # Connection Callbacks
    def on_disconnect(self, reactor):
        """
        Parameters
        ----------
        reactor: Reactor
        """
        self.__q.put((reactor, MqttConnectionEvent.disconnect))

    def on_connect_fail(self, reactor):
        """
        Parameters
        ----------
        reactor: Reactor
        """
        self.__q.put((reactor, MqttConnectionEvent.connect_fail))

    def on_connack(self, reactor, connack):
        """Called immediately upon receiving a `MqttConnack` packet from
        the remote.  The `reactor.state` will be `ReactorState.started`
        or `ReactorState.stopping` if the reactor is shutting down.

        Parameters
        ----------
        reactor: Reactor
        connack: :class:`mqtt_codec.packet.MqttConnack`
        """
        self.__q.put((reactor, connack))

    # Send path
    def on_pubrec(self, reactor, pubrec):
        """Called immediately upon receiving a `MqttPubrec` packet from
        the remote.  This is part of the QoS=2 message send path.

        Parameters
        ----------
        reactor: Reactor
        pubrec: :class:`mqtt_codec.packet.MqttPubrec`
        """
        self.__q.put((reactor, pubrec))

    def on_pubcomp(self, reactor, pubcomp):
        """Called immediately upon receiving a `MqttPubcomp` packet
        from the remote.  This is part of the QoS=2 message send path.

        Parameters
        ----------
        reactor: Reactor
        pubcomp: :class:`mqtt_codec.packet.MqttPubcomp`
        """
        self.__q.put((reactor, pubcomp))

    def on_puback(self, reactor, puback):
        """Called immediately upon receiving a `MqttPuback` packet from
        the remote.  This method is part of the QoS=1 message send path.

        Parameters
        ----------
        reactor: Reactor
        puback: :class:`mqtt_codec.packet.MqttPuback`
        """
        self.__q.put((reactor, puback))

    # Subscribe path
    def on_suback(self, reactor, suback):
        """Called immediately upon receiving a `MqttSuback` packet from
        the remote.

        Parameters
        ----------
        reactor: Reactor
        suback: :class:`mqtt_codec.packet.MqttSuback`
        """
        self.__q.put((reactor, suback))

    def on_unsuback(self, reactor, unsuback):
        """Called immediately upon receiving a `MqttUnsuback` packet
        from the remote.

        Parameters
        ----------
        reactor: Reactor
        unsuback: :class:`mqtt_codec.packet.MqttUnsuback`
        """
        self.__q.put((reactor, unsuback))

    # Receive path
    def on_publish(self, reactor, publish):
        """Called immediately upon receiving a `MqttSuback` packet from
        the remote.  This is part of the QoS=0, 1, and 2 message receive
        paths.

        Parameters
        ----------
        reactor: Reactor
        publish: :class:`mqtt_codec.packet.MqttPublish`
        """
        self.__q.put((reactor, publish))

    def on_pubrel(self, reactor, pubrel):
        """Called immediately upon receiving a `MqttPubrel` packet from
        the remote.  This is part of the QoS=2 message receive path.

        Parameters
        ----------
        reactor: Reactor
        pubrel: :class:`mqtt_codec.packet.MqttPubrel`
        """
        self.__q.put((reactor, pubrel))
