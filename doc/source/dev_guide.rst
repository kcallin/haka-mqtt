================
Developer Guide
================

Building haka-mqtt
===================

Uncontrolled source builds are created in the standard python fashion:

.. code-block:: none

    $ python setup.py sdist
    running sdist
    running egg_info
    writing requirements to haka_mqtt.egg-info/requires.txt
    writing haka_mqtt.egg-info/PKG-INFO
    writing top-level names to haka_mqtt.egg-info/top_level.txt
    writing dependency_links to haka_mqtt.egg-info/dependency_links.txt
    reading manifest file 'haka_mqtt.egg-info/SOURCES.txt'
    writing manifest file 'haka_mqtt.egg-info/SOURCES.txt'
    running check
    creating haka-mqtt-0.1.0-uncontrolled-20180907
    creating haka-mqtt-0.1.0-uncontrolled-20180907/haka_mqtt
    creating haka-mqtt-0.1.0-uncontrolled-20180907/haka_mqtt.egg-info
    [... removed for brevity ...]
    copying tests/test_reactor.py -> haka-mqtt-0.1.0-uncontrolled-20180907/tests
    copying tests/test_scheduler.py -> haka-mqtt-0.1.0-uncontrolled-20180907/tests
    Writing haka-mqtt-0.1.0-uncontrolled-20180907/setup.cfg
    creating dist
    Creating tar archive
    removing 'haka-mqtt-0.1.0-uncontrolled-20180907' (and everything under it)
    $ ls dist
    haka-mqtt-0.1.0-uncontrolled-20180907.tar.gz
    $

The output artifact has the word "uncontrolled" along with a build date
so that users will know the artifact is not a release or from a
continuous integration build server.


Building Documentation
=======================

.. code-block:: none

    $ pip install sphinxcontrib-plantuml enum34 mqtt-codec
    $ make html
    $


Tests
======

The `haka-mqtt` library comes with an extensive battery of tests.  The
tests are built to be as deterministic as possible - to the point that
the loggers are not connected to the system clock so that the time of a
given log message in the tests will be identical from one test run to
the next.

The built-in automated tests can be run from the command-line in the
conventional python manner:

.. code-block:: none

    $ python setup.py test
    $

What is less conventional is that logging to standard output can be
enabled by setting the `LOGGING` environment variable.

.. code-block:: none

    $ LOGGING=true python setup.py test
    $


Docstrings
===========

Python source code is documented according to the the numpy
documentation standard at
https://numpydoc.readthedocs.io/en/latest/format.html.


Requirements
=============

The project will eventually track requirements using a project like
`Pipfile <https://github.com/pypa/pipfile>`_.


