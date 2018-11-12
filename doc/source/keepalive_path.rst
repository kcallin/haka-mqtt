===============
Keepalive Path
===============

The `haka-mqtt` client can be configured to use ``MqttPingreq`` and
``MqttPingresp`` packets to test the liveliness of a connection.  If
the connection does not prove lively the client will disconnect from
the server.
