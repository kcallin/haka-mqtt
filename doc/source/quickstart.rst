===========
Quickstart
===========

Installation through pip is supported:

.. code-block:: bash

   pip install haka-mqtt

A basic mqtt client is short and sweet:

.. literalinclude:: ../../examples/quickstart.py

Typical output of this program is shown::

    2018-11-05 22:30:41,655 haka INFO Starting.
    2018-11-05 22:30:41,655 haka INFO Looking up host test.mosquitto.org:1883.
    2018-11-05 22:30:41,798 haka INFO Found family=inet sock=sock_stream proto=tcp addr=37.187.106.16:1883 (chosen)
    2018-11-05 22:30:41,798 haka INFO Found family=inet6 sock=sock_stream proto=tcp addr=2001:41d0:a:3a10::1:1883
    2018-11-05 22:30:41,798 haka INFO Connecting.
    2018-11-05 22:30:41,798 haka INFO Connected.
    2018-11-05 22:30:41,932 haka INFO Launching message MqttConnect(client_id='bobby', clean_session=True, keep_alive=0s, username=***, password=***, will=None).
    2018-11-05 22:30:41,933 haka INFO Launching message MqttSubscribe(packet_id=0, topics=[Topic('haka', max_qos=1)]).
    2018-11-05 22:30:42,068 haka INFO Received MqttConnack(session_present=False, return_code=<ConnackResult.accepted: 0>).
    2018-11-05 22:30:42,225 haka INFO Received MqttSuback(packet_id=0, results=[<SubscribeResult.qos1: 1>]).
    2018-11-05 22:30:42,225 haka INFO Launching message MqttPublish(packet_id=1, topic='haka', payload=0x7061796c6f6164, dupe=False, qos=1, retain=False).
    2018-11-05 22:30:42,376 haka INFO Received MqttPuback(packet_id=1).
    2018-11-05 22:30:42,552 haka INFO Received MqttPublish(packet_id=1, topic=u'haka', payload=0x7061796c6f6164, dupe=False, qos=1, retain=False).
    2018-11-05 22:30:42,552 haka INFO Stopping.
    2018-11-05 22:30:42,552 haka INFO Launching message MqttDisconnect().
    2018-11-05 22:30:42,552 haka INFO Shutting down outgoing stream.
    2018-11-05 22:30:42,686 haka INFO Remote has gracefully closed remote->local writes; Stopped.
