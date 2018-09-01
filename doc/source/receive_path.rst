=============
Receive Path
=============


QoS 0
======

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
======

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
==============================

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
======

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
