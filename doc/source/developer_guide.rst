================
Developer Guide
================


Distributing haka-mqtt
=======================

The release procedure was created using information from these core sources:

* `PEP 503 - Simple Repository API <https://www.python.org/dev/peps/pep-0503/>`_
* `Python Packaging User Guide <https://packaging.python.org/>`_
* `Twine <https://pypi.org/project/twine/>`_


Build and Publish Release Files
--------------------------------

Ensure there are no old build artifacts.

.. code-block:: none

    $ rm dist/*
    $ ls dist
    $

Create build artifacts.

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
    creating haka-mqtt-0.1.2
    creating haka-mqtt-0.1.2/haka_mqtt
    creating haka-mqtt-0.1.2/haka_mqtt.egg-info
    creating haka-mqtt-0.1.2/tests
    copying files to haka-mqtt-0.1.2...
    copying README.rst -> haka-mqtt-0.1.2
    copying setup.py -> haka-mqtt-0.1.2
    copying haka_mqtt/__init__.py -> haka-mqtt-0.1.2/haka_mqtt
    copying haka_mqtt/clock.py -> haka-mqtt-0.1.2/haka_mqtt
    copying haka_mqtt/mqtt.py -> haka-mqtt-0.1.2/haka_mqtt
    copying haka_mqtt/on_str.py -> haka-mqtt-0.1.2/haka_mqtt
    copying haka_mqtt/reactor.py -> haka-mqtt-0.1.2/haka_mqtt
    copying haka_mqtt/scheduler.py -> haka-mqtt-0.1.2/haka_mqtt
    copying haka_mqtt/socket_factory.py -> haka-mqtt-0.1.2/haka_mqtt
    copying haka_mqtt.egg-info/PKG-INFO -> haka-mqtt-0.1.2/haka_mqtt.egg-info
    copying haka_mqtt.egg-info/SOURCES.txt -> haka-mqtt-0.1.2/haka_mqtt.egg-info
    copying haka_mqtt.egg-info/dependency_links.txt -> haka-mqtt-0.1.2/haka_mqtt.egg-info
    copying haka_mqtt.egg-info/requires.txt -> haka-mqtt-0.1.2/haka_mqtt.egg-info
    copying haka_mqtt.egg-info/top_level.txt -> haka-mqtt-0.1.2/haka_mqtt.egg-info
    copying tests/__init__.py -> haka-mqtt-0.1.2/tests
    copying tests/test_mqtt.py -> haka-mqtt-0.1.2/tests
    copying tests/test_reactor.py -> haka-mqtt-0.1.2/tests
    copying tests/test_scheduler.py -> haka-mqtt-0.1.2/tests
    Writing haka-mqtt-0.1.2/setup.cfg
    Creating tar archive
    removing 'haka-mqtt-0.1.2' (and everything under it)
    $ ls dist
    haka-mqtt-0.1.2.tar.gz
    $


GPG sign build artifacts and verify the signature is good.

.. code-block:: none

    $ gpg --detach-sign -a dist/haka-mqtt-0.1.2.tar.gz

    You need a passphrase to unlock the secret key for
    user: "Keegan Callin <kc@kcallin.net>"
    4096-bit RSA key, ID DD53792F, created 2017-01-01 (main key ID 14BC2EFF)

    gpg: gpg-agent is not available in this session
    $ ls dist
    haka-mqtt-0.1.2.tar.gz  haka-mqtt-0.1.2.tar.gz.asc
    $ gpg --verify dist/haka-mqtt-0.1.2.tar.gz.asc
    gpg: assuming signed data in `dist/haka-mqtt-0.1.2.tar.gz'
    gpg: Signature made Sat 01 Sep 2018 11:00:31 AM MDT using RSA key ID DD53792F
    gpg: Good signature from "Keegan Callin <kc@kcallin.net>" [ultimate]
    Primary key fingerprint: BD51 01F1 9699 A719 E563  6D85 4A4A 7B98 14BC 2EFF
         Subkey fingerprint: BE56 D781 0163 488F C7AE  62AC 3914 0AE2 DD53 792F
    $

Upload to **TEST** PyPI and look at the resulting release page.  You will
not be able to revoke your release if you upload a bad one to PyPI.

.. code-block:: none

    $ twine upload --repository-url https://test.pypi.org/legacy/ dist/*
    Uploading distributions to https://test.pypi.org/legacy/
    Enter your username: kc
    Enter your password:
    Uploading haka-mqtt-0.1.2.tar.gz
    $


Upload to **real** PyPI and verify that the release is complete.

.. code-block:: none

    $ twine upload dist/*


PEP 508 -- Dependency specification for Python Software Packages

PEP-314 -- Metadata for Python Software Packages v1.1


Build and Publish Documentation
--------------------------------

.. code-block:: none

    $ pip install sphinxcontrib-seqdiag
    $ make html
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

Building Documentation
=======================





