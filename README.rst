==========
haka-mqtt
==========

The `haka_mqtt` package is reliable "weapons grade" MQTT client library.
It contains a core mqtt reactor class built with provable reliability,
and reproducibility as its fundamental goals.  A side effect is that the
library turns out to be speedy as well.

Status
=======

The project's core reactor is stable.  It has been tested on systems
with thousands of distributed nodes in difficult field conditions.


Installation
=============

The haka-mqtt package can be from `pypi.org <https://pypi.org>`_ with
`pip <https://pip.pypa.io/en/stable/>`_:

.. code-block:: bash

   pip install haka-mqtt

Usage
======

A quick example of how the package can be used:

.. code-block:: python

    # Standard python Packages
    import logging

    # 3rd-Party Packages
    from haka_mqtt.frontends.poll import (
        MqttPollClientProperties,
        BlockingMqttClient
    )
    from haka_mqtt.reactor import ACTIVE_STATES
    from mqtt_codec.packet import MqttTopic

    LOG_FMT='%(asctime)s %(name)s %(levelname)s %(message)s'
    logging.basicConfig(format=LOG_FMT, level=logging.INFO)

    properties = MqttPollClientProperties()
    properties.host = 'test.mosquitto.org'
    properties.port = 1883
    properties.ssl = False

    TOPIC = 'haka'

    c = BlockingMqttClient(properties)
    c.start()
    sub_ticket = c.subscribe([MqttTopic(TOPIC, 1)])
    c.on_suback = lambda c, suback: c.publish(TOPIC, 'payload', 1)
    c.on_publish = lambda c, publish: c.stop()

    while c.state in ACTIVE_STATES:
        c.poll(5.)


Project Infrastructure
=======================

The project is coordinated through public infrastructure available at
several places:

* `Releases (pypi) <https://pypi.org/project/haka-mqtt>`_
* `Documentation (readthedocs.io) <https://haka-mqtt.readthedocs.io/en/latest/>`_
* `Bug Tracker (github) <https://github.com/kcallin/haka-mqtt/issues>`_
* `Code Repository (github) <https://github.com/kcallin/haka-mqtt>`_
