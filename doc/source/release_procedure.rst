=======================
Distributing haka-mqtt
=======================

The release procedure was created using information from these core sources:

* `PEP 503 - Simple Repository API <https://www.python.org/dev/peps/pep-0503/>`_
* `Python Packaging User Guide <https://packaging.python.org/>`_
* `Twine <https://pypi.org/project/twine/>`_


Documentation
===============

Verify that version and release numbers in ``doc/source/conf.py`` match
``setup.py``.

.. code-block:: bash

    $ grep -e version -e release doc/source/conf.py
    # The short X.Y version
    version = u'1.0.0'
    # The full version, including alpha/beta/rc tags
    release = u'1.0.0'
    $


Make sure copyright dates in ``doc/source/conf.py`` are correct:

.. code-block:: bash

    $ grep -i copyright doc/source/conf.py
    copyright = u'2018 - 2019, Keegan Callin'
    $


Verify requirements document at ``doc/source/requirements.rst`` matches
``setup.py`` (and not the other way around).


Test Release
===============

Clean build directory and ensure there are no old build artifacts.

.. code-block:: none

    $ rm -rf dist build haka_mqtt.egg-info htmlcov
    $ ls dist
    $

It's a common problem to accidentally forget to commit important
changes.  To combat this the ``pyvertest.py`` procedure clones the haka
repository, passes it to a docker container, and runs a test battery in
a set of environments.

.. code-block:: none

    $ ./pyvertest.py
    [... removed for brevity ...]
    pip install python:3.7-alpine3.8
    docker run --rm -v /home/kcallin/src/haka-mqtt:/haka-mqtt python:3.7-alpine3.8 pip install /haka-mqtt
    Processing /haka-mqtt
    Building wheels for collected packages: haka-mqtt, mqtt-codec
      Running setup.py bdist_wheel for haka-mqtt: started
      Running setup.py bdist_wheel for haka-mqtt: finished with status 'done'
      Stored in directory: /root/.cache/pip/wheels/c5/b3/fa/e30017929f15cb43137c499453ff45f3754db112f34a52cb9d
      Running setup.py bdist_wheel for mqtt-codec: started
      Running setup.py bdist_wheel for mqtt-codec: finished with status 'done'
      Stored in directory: /root/.cache/pip/wheels/b7/6b/0f/5fb8026a75541fb9fcdec2f3fc33b75aad929b48e85eca68a9
    Successfully built haka-mqtt mqtt-codec
    Installing collected packages: mqtt-codec, haka-mqtt
    Successfully installed haka-mqtt-0.3.0-uncontrolled-20181217 mqtt-codec-1.0.1
    Return code 0
    Removing container id b9d481a9f49b966fa6708e1ef9fda16d0142b35a7613fc794a43105b0eb6eb2b.
    Removing temp directory /tmp/tmput2xuulf.
    > 10/10 okay.


Ensure that CHANGELOG.rst has release version and release date correct
as well as release content listed.

.. code-block:: bash

    $ vi CHANGELOG.rst
    $ git commit -S CHANGELOG.rst


Create test release artifacts.

.. code-block:: none

    $ python setup.py egg_info -D -b 'a' sdist
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
    [... removed for brevity ...]
    copying tests/test_reactor.py -> haka-mqtt-0.1.2/tests
    copying tests/test_scheduler.py -> haka-mqtt-0.1.2/tests
    Writing haka-mqtt-0.1.2/setup.cfg
    Creating tar archive
    removing 'haka-mqtt-0.1.2' (and everything under it)
    $ ls dist
    haka-mqtt-0.1.2.tar.gz
    $


GPG signatures are created for test release artifacts.

.. code-block:: none

    $ gpg2 --detach-sign -a dist/*

    You need a passphrase to unlock the secret key for
    user: "Keegan Callin <kc@kcallin.net>"
    4096-bit RSA key, ID DD53792F, created 2017-01-01 (main key ID 14BC2EFF)

    gpg: gpg-agent is not available in this session
    $ ls dist
    haka-mqtt-0.1.2.tar.gz  haka-mqtt-0.1.2.tar.gz.asc
    $ gpg2 --verify dist/*.asc
    gpg: assuming signed data in `dist/haka-mqtt-0.1.2.tar.gz'
    gpg: Signature made Sat 01 Sep 2018 11:00:31 AM MDT using RSA key ID DD53792F
    gpg: Good signature from "Keegan Callin <kc@kcallin.net>" [ultimate]
    Primary key fingerprint: BD51 01F1 9699 A719 E563  6D85 4A4A 7B98 14BC 2EFF
         Subkey fingerprint: BE56 D781 0163 488F C7AE  62AC 3914 0AE2 DD53 792F
    $


.. https://packaging.python.org/guides/making-a-pypi-friendly-readme/#validating-restructuredtext-markup
   (Retrieved 2018-11-28)

Ensure that twine version 1.12.0 or high is installed:

.. code-block:: none

    $ twine --version
    twine version 1.12.0 (pkginfo: 1.4.2, requests: 2.20.1, setuptools: 40.6.2,
    requests-toolbelt: 0.8.0, tqdm: 4.28.1)


Verify that distribution passes twine checks:

.. code-block:: none

    $ twine check dist/*
    Checking distribution dist/haka-mqtt-1.0.0.tar.gz: Passed


Release artifacts are uploaded to **TEST** PyPI.

.. code-block:: none

    $ twine upload --repository-url https://test.pypi.org/legacy/ dist/*
    Uploading distributions to https://test.pypi.org/legacy/
    Enter your username: kc
    Enter your password:
    Uploading haka-mqtt-0.1.2.tar.gz
    $


The resulting `TestPyPI entry <https://test.pypi.org/project/haka-mqtt/>`_
should be inspected for correctness.  "The database for TestPyPI may be
periodically pruned, so it is not unusual for user accounts to be
deleted [#]_".  Packages on **TEST** PyPI and **real** PyPI cannot be
removed upon distributor demand.  On **TEST** PyPI packages may be
removed on prune, on **real** PyPI they will remain forever.  A
checklist to help verify the PyPI release page follows:

* Version Number is Correct
* Documentation Link is Correct
* ReST README.rst is rendered correctly on the front page.


After the checklist is complete then it is time to upload to **real**
PyPI and verify that the release is complete.  There is no undoing
this operation.  Think Carefully.


PEP 508 -- Dependency specification for Python Software Packages

PEP-314 -- Metadata for Python Software Packages v1.1

.. [#] `Test PyPI, Registering Your Account <https://packaging.python.org/guides/using-testpypi/#registering-your-account>`_,
       retrieved 2018-09-07.

Official Release
=================

Create, sign, and push release tag:

.. code-block:: bash

    $ git tag -s v0.1.0
    $ git push origin v0.1.0


Remove test artifacts:

.. code-block:: bash

    $ rm -rf dist build haka_mqtt.egg-info htmlcov
    $ ls dist
    $


Create official release artifacts.

.. code-block:: none

    $ python setup.py egg_info -D -b '' sdist
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
    [... removed for brevity ...]
    copying tests/test_reactor.py -> haka-mqtt-0.1.2/tests
    copying tests/test_scheduler.py -> haka-mqtt-0.1.2/tests
    Writing haka-mqtt-0.1.2/setup.cfg
    Creating tar archive
    removing 'haka-mqtt-0.1.2' (and everything under it)
    $ ls dist
    haka-mqtt-0.1.2.tar.gz
    $


GPG sign official release artifact:

.. code-block:: none

    $ gpg2 --detach-sign -a dist/*

    You need a passphrase to unlock the secret key for
    user: "Keegan Callin <kc@kcallin.net>"
    4096-bit RSA key, ID DD53792F, created 2017-01-01 (main key ID 14BC2EFF)

    gpg: gpg-agent is not available in this session
    $ ls dist
    haka-mqtt-0.1.2.tar.gz  haka-mqtt-0.1.2.tar.gz.asc
    $ gpg2 --verify dist/*.asc
    gpg: assuming signed data in `dist/haka-mqtt-0.1.2.tar.gz'
    gpg: Signature made Sat 01 Sep 2018 11:00:31 AM MDT using RSA key ID DD53792F
    gpg: Good signature from "Keegan Callin <kc@kcallin.net>" [ultimate]
    Primary key fingerprint: BD51 01F1 9699 A719 E563  6D85 4A4A 7B98 14BC 2EFF
         Subkey fingerprint: BE56 D781 0163 488F C7AE  62AC 3914 0AE2 DD53 792F
    $


The access credentials in `~/.pypirc` contains the username/password
that twine uses for PyPI.

.. code-block:: none

    $ cat ~/.pypirc
    [distutils]
    index-servers =
        pypi

    [pypi]
    username:<XXXXXX>
    password:<XXXXXX>
    $ twine upload dist/*


Distribute Documentation
===========================

Documentation is distributed through
`readthedocs.org <https://haka-mqtt.readthedocs.io/en/latest>`_.  After
a release visit the `haka-mqtt readthedocs project <https://readthedocs.org/projects/haka-mqtt/>`_,
select "Versions" click on "inactive" versions and make sure that the
correct versions are marked as "Active".

The ``haka-mqtt`` project documentation uses
`PlantUML <https://pypi.org/project/plantuml/>`_ to draw diagrams and
this package is not support out-of-the-box by `readthedocs`.  The
project root directory contains a ``.readthedocs.yml`` file to set the
build `readthedocs` build environment to one that supports PlantUML and
bypass the problem.


Increment Version Number
=========================

The release number in `setup.py` has been consumed and should never be
used again.  Take the time to increment the number, commit the change,
then push the change.

.. code-block:: none

    $ vi setup.py
    $ vi doc/source/conf.py
    $ git commit setup.py
    $ git push origin master
