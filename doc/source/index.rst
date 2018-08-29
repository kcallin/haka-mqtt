.. Haka MQTT documentation master file, created by
   sphinx-quickstart on Tue Aug 21 10:43:08 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

=====================================
Welcome to Haka MQTT's documentation!
=====================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   modules

This is a message sequence diagram.


Receive Path
=============


QoS 0
------

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; S;

           H <- S [diagonal, label = "Publish"];
      C <- H [label="on_publish call"];
      C -> H [label="on_publish return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      S [description="MQTT Server"];
   }


QoS 1
------

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

QoS 1 with Pre-Ack Disconnect
-------------------------------

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

QoS 2
------

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

Send Path
==========

QoS 0
------

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; S;

      C -> H [label="publish call"];
           H -> S [diagonal, label = "Publish"];
      C <- H [label="publish return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      S [description="MQTT Server"];
   }

QoS 1
------

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q; S;

      C -> H [label="publish call"];
           H -> Q [diagonal, label = "Publish"];
      C <- H [label="publish return"];
           H <- S [diagonal, label = "Puback"];
      C <- H [label="on_puback call"];
      C -> H [label="on_puback return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      Q [description="Output Queue"];
      S [description="MQTT Server"];
   }


QoS 1 w/Disconnect
-------------------

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q; S;

      C -> H [label="publish call"];
           H -> Q [diagonal, label = "Publish"];
      C <- H [label="publish return"];
      === Disconnect ===
      ... <Contents of output queue disarded; Connection preamble> ...
           H -> Q [diagonal, label = "Publish"];
           H <- S [diagonal, label = "Puback"];
      C <- H [label="on_puback call"];
      C -> H [label="on_puback return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      Q [description="Output Queue"];
      S [description="MQTT Server"];
   }


QoS 2
------

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q; S;

      C -> H [label="publish call"];
           H -> Q [diagonal, label = "Publish"];
      C <- H [label="publish return"];
           H <- S [diagonal, label = "Pubrec"];
      C <- H [label="on_pubrec call"];
      C -> H [label="on_pubrec return"];
           H -> Q [diagonal, label = "Pubrel"];
           H <- S [diagonal, label = "Pubcomp"];
      C <- H [label="on_pubcomp call"];
      C -> H [label="on_pubcomp return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      Q [description="Output Queue"];
      S [description="MQTT Server"];
   }


Subscribe
----------

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q; S;

      C -> H [label="subscribe(topic=T)"]
           H -> Q [label="subscribe(topic=T)"]
           H <- S [diagonal, label="Publish(topic=T)"];
           H <- S [diagonal, label="Publish(topic=T)"];
           H <- S [diagonal, label="Publish(topic=T)"];
           H <- S [diagonal, label="Suback(topic=T)"];
      C <- H [label="on_suback call"];
      C -> H [label="on_suback return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      Q [description="Output Queue"];
      S [description="MQTT Server"];
   }


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
