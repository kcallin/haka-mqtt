===============
Subscribe Path
===============


Subscribe
==========

The subscribe/suback sequence shows the potential for a publish publish
for the newly subscribed topic before the suback packet arrives.

.. seqdiag::
   :desctable:

   seqdiag {
      activation = none;

      C; H; Q; S;

      C -> H [label="subscribe(topic=T)"]
           H -> Q [label="subscribe(topic=T)"]
           H <- S [diagonal, label="Publish(topic=T)", note="Publish messages may begin arriving before suback."];
      C <- H [label="on_publish call"];
      C -> H [label="on_publish return"];
           H <- S [diagonal, label="Suback(topic=T)"];
      C <- H [label="on_suback call"];
      C -> H [label="on_suback return"];

      C [description="Client"];
      H [description="haka-mqtt"];
      Q [description="Output Queue"];
      S [description="MQTT Server"];
   }
