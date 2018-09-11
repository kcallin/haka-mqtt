=========
Stopping
=========

When a stop is ordered the haka-mqtt reactor is put into a ``stopping``
state.  The ``stopping`` state is the prelude to the ``stopped`` state.
While stopping:

#. Wait until any message that has been partially written to output
   buffers is completely transmitted to the output buffer.
#. Write a ``MqttDisconnect`` message to the output buffer.
#. Wait until the ``MqttDisconnect`` message has been written to the
   output buffer.
#. Close socket writes.
#. Process messages on input until the remote closes its write stream
   and there is no more data left to read.
#. Enter stopped state.


Start
======

While in the ``stopping`` state calls to start have no effect.


Stop
=====

While in the ``stopping`` state calls to stop have no further effect.


Subscribe/Unsubscribe
======================

While in the ``stopping`` state subscribe and unsubscribe calls have no
effect.  Any messages for previous subscribe and unsubscribe calls that
are not yet in flight (they are in the pre-flight queue) will be
discarded.  Callbacks to ``on_suback`` and ``on_unsuback`` will only be
made for in-flight messages that the server responds to; subscribe and
unsubscribe messages in pre-flight will be dropped.


Publish
========

Calls to publish ``stopping`` state will add ``MqttPublish`` packets to
the pre-flight queue but these packets will not be delivered to the
server before a disconnect.  A successfull reconnection beginning with
a call to start will see them subseuqently delivered.
