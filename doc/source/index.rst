.. Haka MQTT documentation master file, created by
   sphinx-quickstart on Tue Aug 21 10:43:08 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

===================================
`haka-mqtt` Project Documentation
===================================

The `haka_mqtt` package is reliable "weapons grade" MQTT client library.
It contains a core mqtt reactor class built with provable reliability,
and reproducibility as its fundamental goals.  It turns out that it is
sufficiently speedy as well; there has never been a performance
complaint lodged.


Status
=======

The project's core reactor is stable.  It has been tested on systems
with thousands of distributed nodes in difficult field conditions.  The
QoS=0 and QoS=1 datapaths are particularly well tested.  The QoS=2 data
has been field tested as thoroughly as the QoS=0 and Qos=1 data paths.

While the core reactor is very well tested the frontends are less
tested.  You should pay attention to notes on the different frontends
regarding their status and use.


Installation
=============

The haka-mqtt package is distributed through
`pypi.org <https://pypi.org>`_ and can be installed with the standard
Python package manager `pip <https://pip.pypa.io/en/stable/>`_:

.. code-block:: bash

   $ pip install haka-mqtt

If you do not have pip then the package can be downloaded from
`haka-mqtt <https://pypi.org/project/haka-mqtt>`_ and installed with
the standard `setup.py` method:

.. code-block:: bash

   $ python setup.py install


Project Infrastructure
=======================

The project is coordinated through public infrastructure available at
several places:

* `Releases (pypi) <https://pypi.org/project/haka-mqtt>`_
* `Documentation (readthedocs.io) <https://haka-mqtt.readthedocs.io/en/latest/>`_
* `Bug Tracker (github) <https://github.com/kcallin/haka-mqtt/issues>`_
* `Code Repository (github) <https://github.com/kcallin/haka-mqtt>`_


Table of Contents
==================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   user_guide
   haka_mqtt
   changelog
   dev_guide
   release_procedure


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


