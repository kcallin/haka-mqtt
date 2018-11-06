===========================
Subscribe/Unsubscribe Path
===========================


Subscribe
==========

The subscribe/suback sequence shows the potential for a publish publish
for the newly subscribed topic before the suback packet arrives.


.. uml::

    Client -> Haka: subscribe call
    note right: subscribe(topic=T) packet enqueued.
    Client <- Haka: subscribe return
    == ... ==
    Client -> Haka: write call
              Haka -> Socket: send subscribe
    note right: subscribe packet transferred to socket write buffer.
    Client <- Haka: write return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv publish(topic=T, QoS=0)
    note right: publish(topic=T) may arrive before suback!
    Client <- Haka: on_publish call
    Client -> Haka: on_publish return
    Client <- Haka: read return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv suback(topic=T)
    Client <- Haka: on_suback call
    Client -> Haka: on_suback return
    Client <- Haka: read return


Unsubscribe Path
=================

The unsubscribe/unsuback sequence is very similar to the
subscribe/suback sequence.

.. uml::

    Client -> Haka: unsubscribe call
    note right: unsubscribe packet enqueued.
    Client <- Haka: unsubscribe return
    == ... ==
    Client -> Haka: write call
              Haka -> Socket: send unsubscribe
    note right: unsubscribe packet transferred to socket write buffer.
    Client <- Haka: write return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv unsuback
    Client <- Haka: on_unsuback call
    Client -> Haka: on_unsuback return
    Client <- Haka: read return
