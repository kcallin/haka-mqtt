===============
Keepalive Path
===============

The `haka-mqtt` client can be configured to use ``MqttPingreq`` and
``MqttPingresp`` packets to test the liveliness of a connection.  If
the connection does not prove lively the client will disconnect from
the server.

Receive Path
=============

If the core reactor does not receive any bytes on the TCP socket for
:attr:`haka_mqtt.reactor.Reactor.recv_idle_ping_period` seconds then
a ``MqttPingreq`` packet will be launched.  If after
:attr:`haka_mqtt.reactor.Reactor.recv_idle_abort_period` seconds no
bytes have been received then the reactor terminates the connection and
enters an error state.

Send Path
==========

If the core reactor does not send and bytes on the underlying socket
for :attr:`haka_mqtt.reactor.Reactor.keepalive_period` seconds then
a ``MqttPingreq`` packet will be launched.  The server will disconnect
the client if it does not receive any packets after
1.5 times :attr:`haka_mqtt.reactor.Reactor.keepalive_period` seconds
[MQTT-3.1.2-24].  The client will detect this as a network
disconnection.