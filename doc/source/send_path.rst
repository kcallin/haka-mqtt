==========
Send Path
==========

QoS 0
======


.. uml::

    Client -> Haka: publish call (QoS=0)
    note right: publish packet enqueued.
    Client <- Haka: publish return
    Client -> Haka: write call
              Haka -> Socket: send publish
    note right: publish packet transferred to socket write buffer and dequeued.
    Client <- Haka: write return


QoS 1
======

.. uml::

    Client -> Haka: publish call (QoS=1)
    note right: publish packet enqueued.
    Client <- Haka: publish return
    Client -> Haka: write call
              Haka -> Socket: send publish
    note right: publish packet transferred to socket write buffer.
    Client <- Haka: write return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv puback
    note right: publish packet dequeued.
    Client <- Haka: read return


QoS 1 w/Disconnect
===================

.. uml::

    Client -> Haka: publish call (QoS=1)
    note right: publish packet enqueued.
    Client <- Haka: publish return
    Client -> Haka: write call
              Haka -> Socket: send publish
    note right: publish packet transferred to socket write buffer.
    Client <- Haka: write return
    == socket disconnect, reactor start ==
    Client -> Haka: write call
              Haka -> Socket: send publish(dupe=True)
    note right: publish packet transferred to socket write buffer.
    Client <- Haka: write return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv puback
    note right: publish packet dequeued.
    Client <- Haka: read return


QoS 2
======

.. uml::

    Client -> Haka: publish call (QoS=2)
    note right: publish packet enqueued.
    Client <- Haka: publish return
    Client -> Haka: write call
              Haka -> Socket: send publish
    note right: publish packet transferred to socket write buffer.
    Client <- Haka: write return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv pubrec
    Client <- Haka: on_pubrec call
    Client -> Haka: on_pubrec return
    note right: pubrel packet queued.
    Client <- Haka: read return
    == ... ==
    Client -> Haka: write call
              Haka -> Socket: send pubrel
    Client <- Haka: write return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv pubcomp
    note right: publish packet dequeued.
    Client <- Haka: on_pubcomp call
    Client -> Haka: on_pubcomp return
    Client <- Haka: read return


QoS 2 w/Publish Disconnect
===========================

.. uml::

    Client -> Haka: publish call (QoS=2)
    note right: publish packet enqueued.
    Client <- Haka: publish return
    Client -> Haka: write call
              Haka -> Socket: send publish
    note right: publish packet transferred to socket write buffer.
    Client <- Haka: write return
    == socket disconnect, reactor start ==
    Client -> Haka: write call
              Haka -> Socket: send publish(dupe=True)
    note right: publish packet transferred to socket write buffer.
    Client <- Haka: write return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv pubrec
    Client <- Haka: on_pubrec call
    Client -> Haka: on_pubrec return
    note right: pubrel packet queued.
    Client <- Haka: read return
    == ... ==
    Client -> Haka: write call
              Haka -> Socket: send pubrel
    Client <- Haka: write return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv pubcomp
    note right: publish packet dequeued.
    Client <- Haka: on_pubcomp call
    Client -> Haka: on_pubcomp return
    Client <- Haka: read return


QoS 2 w/Pubrel Disconnect
==========================

.. uml::

    Client -> Haka: publish call (QoS=2)
    note right: publish packet enqueued.
    Client <- Haka: publish return
    Client -> Haka: write call
              Haka -> Socket: send publish
    note right: publish packet transferred to socket write buffer.
    Client <- Haka: write return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv pubrec
    Client <- Haka: on_pubrec call
    Client -> Haka: on_pubrec return
    note right: pubrel packet queued.
    Client <- Haka: read return
    == ... ==
    Client -> Haka: write call
              Haka -> Socket: send pubrel
    Client <- Haka: write return
    == socket disconnect, reactor start ==
    Client -> Haka: write call
              Haka -> Socket: send pubrel
    note right: pubrel packet transferred to socket write buffer.
    Client <- Haka: write return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv pubcomp
    note right: publish packet dequeued.
    Client <- Haka: on_pubcomp call
    Client -> Haka: on_pubcomp return
    Client <- Haka: read return
