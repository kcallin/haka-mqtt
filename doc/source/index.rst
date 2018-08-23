.. Haka MQTT documentation master file, created by
   sphinx-quickstart on Tue Aug 21 10:43:08 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Haka MQTT's documentation!
=====================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   modules

This is a message sequence diagram.


Client Publish QoS 1 Message
-----------------------------

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      H; S;

      H -> S [diagonal, label = "Publish"];
      H <- S [diagonal, label = "Puback"];

      H [description="haka-mqtt"];
      S [description="MQTT Server"];
   }


Client Receives QoS 1 Message
-----------------------------

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; S;

           H <- S [diagonal, label = "Publish"];
      C <- H [label="on_publish call"];
      C -> H [label="on_publish return"];
           H -> S [diagonal, label = "Puback"];

      C [description="Client"];
      H [description="haka-mqtt"];
      S [description="MQTT Server"];
   }


Client Receives QoS 1 Message with Disconnect
---------------------------------------------

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; S;

           H <- S [diagonal, label = "Publish"];
      C <- H [label="on_publish call"];
      C -> H [label="on_publish return"];
      === Disconnect ===
           H <- S [diagonal, label = "Publish"];
      C <- H [label="on_publish call"];
      C -> H [label="on_publish return"];
           H -> S [diagonal, label = "Puback"];

      C [description="Client"];
      H [description="haka-mqtt"];
      S [description="MQTT Server"];
   }


Client Publishes QoS 2 Message
-------------------------------

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C -> S [diagonal, label = "Publish"];
      C <- S [diagonal, label = "Pubrec"];
      C -> S [diagonal, label = "Pubrel"];
      C <- S [diagonal, label = "Pubcomp"];
      C [description = "haka-MQTT Client"];
      S [description = "MQTT Server"];
   }

Client Receives QoS 2 Message
-----------------------------

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; S;

           H <- S [diagonal, label = "Publish"];
      C <- H [label="on_publish call"];
      C -> H [label="on_publish return"];
           H -> S [diagonal, label = "Pubrec"];
           H <- S [diagonal, label = "Pubrel"];
      C <- H [label="on_pubrel call"];
      C -> H [label="on_pubrel return"];
           H -> S [diagonal, label = "Pubcomp"];

      C [description="Client"];
      H [description="haka-mqtt"];
      S [description="MQTT Server"];
   }


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
