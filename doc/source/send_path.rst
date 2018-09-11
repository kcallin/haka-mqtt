==========
Send Path
==========

QoS 0
======

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q;

      C -> H [label="publish call"];
           H -> Q [label = "Publish"];
      C <- H [label="publish return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      Q [description="Output Queue"];
   }

QoS 1
======

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q; S;

      C -> H [label="publish call"];
           H -> Q [label = "Publish"];
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
===================

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q; S;

      C -> H [label="publish call"];
           H -> Q [label = "Publish"];
      C <- H [label="publish return"];
      === Disconnect ===
      ... <Contents of output queue disarded; Connection preamble> ...
           H -> Q [label = "Publish"];
           H <- S [diagonal, label = "Puback"];
      C <- H [label="on_puback call"];
      C -> H [label="on_puback return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      Q [description="Output Queue"];
      S [description="MQTT Server"];
   }


QoS 2
======

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q; S;

      C -> H [label="publish call"];
           H -> Q [label = "Publish"];
      C <- H [label="publish return"];
           H <- S [diagonal, label = "Pubrec"];
      C <- H [label="on_pubrec call"];
      C -> H [label="on_pubrec return"];
           H -> Q [label = "Pubrel"];
           H <- S [diagonal, label = "Pubcomp"];
      C <- H [label="on_pubcomp call"];
      C -> H [label="on_pubcomp return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      Q [description="Output Queue"];
      S [description="MQTT Server"];
   }


QoS 2 w/Publish Disconnect
===========================

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q; S;

      C -> H [label="publish call"];
           H -> Q [label = "Publish"];
      C <- H [label="publish return"];
      === Disconnect ===
      ... <Contents of output queue disarded; Connection preamble> ...
           H -> Q [label = "Publish"];
           H <- S [diagonal, label = "Pubrec"];
      C <- H [label="on_pubrec call"];
      C -> H [label="on_pubrec return"];
           H -> Q [label = "Pubrel"];
           H <- S [diagonal, label = "Pubcomp"];
      C <- H [label="on_pubcomp call"];
      C -> H [label="on_pubcomp return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      Q [description="Output Queue"];
      S [description="MQTT Server"];
   }


QoS 2 w/Pubrel Disconnect
==========================

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q; S;

      C -> H [label="publish call"];
           H -> Q [label = "Publish"];
      C <- H [label="publish return"];
           H <- S [diagonal, label = "Pubrec"];
      C <- H [label="on_pubrec call"];
      C -> H [label="on_pubrec return"];
           H -> Q [label = "Pubrel"];
      === Disconnect ===
      ... <Contents of output queue disarded; Connection preamble> ...
           H -> Q [label = "Pubrel"];
           H <- S [diagonal, label = "Pubcomp"];
      C <- H [label="on_pubcomp call"];
      C -> H [label="on_pubcomp return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      Q [description="Output Queue"];
      S [description="MQTT Server"];
   }

Maximum Publishes In-Flight
============================
