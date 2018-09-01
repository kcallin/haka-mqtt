===============
Subscribe Path
===============


Subscribe
==========

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q; S;

      C -> H [label="subscribe(topic=T)"]
           H -> Q [label="subscribe(topic=T)"]
           H <- S [diagonal, label="Publish(topic=T)", note="Publish messages may begin arriving before suback."];
           H <- S [diagonal, label="Publish(topic=T)"];
           H <- S [diagonal, label="Suback(topic=T)"];
      C <- H [label="on_suback call"];
      C -> H [label="on_suback return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      Q [description="Output Queue"];
      S [description="MQTT Server"];
   }
