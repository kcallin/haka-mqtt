=============
Receive Path
=============


QoS 0
======


.. uml::

    Client -> Haka: read call
              Haka <- Socket: recv publish(QoS=0)
    Client <- Haka: on_publish call
    Client -> Haka: on_publish return
    Client <- Haka: read return


QoS 1
======

.. uml::

    Client -> Haka: read call
              Haka <- Socket: recv publish(QoS=1)
    Client <- Haka: on_publish call
    Client -> Haka: on_publish return
    note right: enqueue puback
    Client <- Haka: read return
    == ... ==
    Client -> Haka: write call
              Haka -> Socket: send puback
    note right: dequeue puback
    Client <- Haka: write return


QoS 1 with Pre-Ack Disconnect
==============================

.. uml::

    Client -> Haka: read call
              Haka <- Socket: recv publish(QoS=1)
    Client <- Haka: on_publish call
    Client -> Haka: on_publish return
    note right: enqueue puback
    Client <- Haka: read return
    == socket disconnect, reactor start, puback cleared ==
    Client -> Haka: read call
              Haka <- Socket: recv publish(QoS=1, dupe=True)
    Client <- Haka: on_publish call
    Client -> Haka: on_publish return
    note right: enqueue puback
    Client <- Haka: read return
    == ... ==
    Client -> Haka: write call
              Haka -> Socket: send puback
    note right: dequeue puback
    Client <- Haka: write return


QoS 2
======

.. uml::

    Client -> Haka: read call
              Haka <- Socket: recv publish(QoS=2)
    Client <- Haka: on_publish call
    Client -> Haka: on_publish return
    note right: enqueue pubrec
    Client <- Haka: read return
    == ... ==
    Client -> Haka: write call
              Haka -> Socket: send pubrec
    note right: dequeue pubrec
    Client <- Haka: write return
    == ... ==
    Client -> Haka: read call
              Haka <- Socket: recv pubrel
    Client <- Haka: on_pubrel call
    Client -> Haka: on_pubrel return
    note right: enqueue pubcomp
    Client <- Haka: read return
    == ... ==
    Client -> Haka: write call
              Haka -> Socket: send pubcomp
    note right: dequeue pubcomp
    Client <- Haka: write return
