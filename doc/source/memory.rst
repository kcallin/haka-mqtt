=============
Memory Usage
=============


Send Path
==========

The core MQTT Reactor wraps an outgoing message queue.  Maximum memory
usage should be be bounded by about 2x the byte size of the outgoing
message queue.

Receive Path
=============

The peak receive path memory usage on the order of 2x the maximum MQTT
message size.  In MQTT 3.1.1 the maximum message length is
:attr:`mqtt_codec.packet.MqttFixedHeader.MAX_REMAINING_LEN`
(268435455 bytes) so the maximum memory usage will be about 512MB.
Typical MQTT messages are much smaller than this so peak memory usage
will likewise be much smaller.

A possible future enhancement to the reactor could be to set a maximum
receive message size lower than the protocol maximum.
