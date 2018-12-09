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


Coverage
=========

Test coverage is monitored using
`coverage.py <https://coverage.readthedocs.io>`_ version 4.5 or higher.
Normally this can be installed through your operating system's package
manager (like rpm or apt-get) or by using `pip`.  A coverage
configuration file is included at `.coveragerc` and the tool can be run
in this fashion:

.. code-block:: none

    $ coverage run setup.py test
    running test
    Searching for mock
    Best match: mock 2.0.0
    Processing mock-2.0.0-py2.7.egg

    Using /home/kcallin/src/haka-mqtt/.eggs/mock-2.0.0-py2.7.egg
    Searching for pbr>=0.11
    Best match: pbr 4.2.0
    Processing pbr-4.2.0-py2.7.egg

    Using /home/kcallin/src/haka-mqtt/.eggs/pbr-4.2.0-py2.7.egg
    running egg_info
    writing requirements to haka_mqtt.egg-info/requires.txt
    writing haka_mqtt.egg-info/PKG-INFO
    writing top-level names to haka_mqtt.egg-info/top_level.txt
    writing dependency_links to haka_mqtt.egg-info/dependency_links.txt
    reading manifest file 'haka_mqtt.egg-info/SOURCES.txt'
    writing manifest file 'haka_mqtt.egg-info/SOURCES.txt'
    running build_ext
    test_connack (tests.test_reactor_keepalive.TestKeepalive) ... ok
    test_connected (tests.test_reactor_keepalive.TestKeepalive) ... ok
    test_connected_keepalive_with_recv_qos0 (tests.test_reactor_keepalive.TestKeepalive) ... ok
    test_connected_unsolicited_pingresp (tests.test_reactor_keepalive.TestKeepalive) ... ok
    [... removed for brevity...]
    test_repeat (tests.test_cycle_iter.TestIterCycles) ... ok
    test_scheduler (tests.test_scheduler.TestScheduler) ... ok
    test_scheduler_0 (tests.test_scheduler.TestScheduler) ... ok

    ----------------------------------------------------------------------
    Ran 95 tests in 0.376s

    OK
    $ coverage report
    Name                        Stmts   Miss Branch BrPart  Cover
    -------------------------------------------------------------
    haka_mqtt/__init__.py           0      0      0      0   100%
    haka_mqtt/clock.py             13      1      0      0    92%
    haka_mqtt/cycle_iter.py        16      0      2      0   100%
    haka_mqtt/exception.py          4      0      0      0   100%
    haka_mqtt/mqtt_request.py      89      2      6      2    96%
    haka_mqtt/null_log.py          15      7      0      0    53%
    haka_mqtt/on_str.py            17      3      4      1    71%
    haka_mqtt/packet_ids.py        22      2      4      2    85%
    haka_mqtt/reactor.py          945     83    316     29    90%
    haka_mqtt/scheduler.py         75     11     12      1    84%
    haka_mqtt/selector.py          11      0      0      0   100%
    -------------------------------------------------------------
    TOTAL                        1207    109    344     35    89%


Docstrings
===========

Python source code is documented according to the the numpy
documentation standard at
https://numpydoc.readthedocs.io/en/latest/format.html.


Requirements
=============

The project will eventually track requirements using a project like
`Pipfile <https://github.com/pypa/pipfile>`_.


