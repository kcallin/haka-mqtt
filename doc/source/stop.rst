=========
Stopping
=========

A `stop` call puts the haka-mqtt reactor into a stop procedure:

1. Reactor enters ``stopping`` state.
2. ``MqttDisconnect`` is inserted into the output queue.
3. Wait until all messages preceding and the ``MqttDisconnect`` message
   itself have been written to the output buffer.
4. Close socket writes.
5. Reactor enters ``mute`` state.
6. Process messages on input until the remote closes its write stream
   and there is no more data left to read.
7. Enter ``stopped`` state.


Start
======

While in the ``stopping`` or ``mute`` states calls to start have no
effect.


Stop
=====

While in the ``stopping`` or ``mute`` states calls to stop have no
further effect.


Subscribe/Unsubscribe
======================

Calls made to subscribe/unsubscribe made prior to a ``stop`` call will
have their associated packets delivered to the server before the reactor
enters its ``mute`` state.  Callbacks to ``on_suback`` and
``on_unsuback`` will only be made for whatever acks are received prior
to the reactor entering a final state.  Calls to subscribe/unsubscribe
made after a ``stop`` call place packets on the preflight queue but
these packets will not be delivered before the reactor enters ``mute``
state and the packets will eventually be discarded if the reactor is
restarted after entering a final state.



Publish
========

Calls to publish ``stopping`` state will add ``MqttPublish`` packets to
the pre-flight queue but these packets will not be delivered to the
server before a disconnect.  A successfull reconnection beginning with
a call to start will see them subseuqently delivered.
