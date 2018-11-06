==================
Reactor Lifecycle
==================

This is a uml diagram.

.. graphviz::

    digraph START {
        node [shape=circle,fontsize=8,fixedsize=true,width=0.9];
        edge [fontsize=8];
        rankdir=LR;

        "init" [shape="doublecircle"];
        "stopped" [shape="doublecircle"];
        "error" [shape="doublecircle"];

        subgraph cluster0 {
            graph[style="invisible"];

            "init" -> "starting" [label="start"];
            "starting" -> "started";
            "started" -> "stopping" [label="stop"];
            "stopping" -> "stopped";
        }

        "error" -> "starting" [label="start"];

        "stopped" -> "starting" [label="start"];
        "starting" -> "starting" [label="start"];
        "started" -> "started" [label="start"];
        "stopping" -> "stopping" [label="start"];
    }


.. graphviz::

    digraph TERMINATE {
        node [shape=circle,fontsize=8,fixedsize=true,width=0.9];
        edge [fontsize=8];
        rankdir=LR;

        "init" [shape="doublecircle"];
        "stopped" [shape="doublecircle"];
        "error" [shape="doublecircle"];

        "init" -> "starting" [label="start"];
        "starting" -> "started";
        "started" -> "stopping" [label="stop"];
        "stopping" -> "stopped";

        "init" -> "stopped" [label="terminate"];
        "starting" -> "stopped" [label="terminate"];
        "started" -> "stopped" [label="terminate"];
        "stopping" -> "stopped"  [label="terminate"];
    }


.. graphviz::

    digraph STOP {
        node [shape=circle,fontsize=8,fixedsize=true,width=0.9];
        edge [fontsize=8];
        rankdir=LR;

        "init" [shape="doublecircle"];
        "stopped" [shape="doublecircle"];
        "error" [shape="doublecircle"];

        "init" -> "starting" [label="start"];
        "starting" -> "started";
        "started" -> "stopping" [label="stop"];
        "stopping" -> "stopped";

        "init" -> "stopped" [label="stop"];
        "starting" -> "stopping" [label="stop"];
        "stopping" -> "stopping"  [label="stop"];
    }




Start
======

When the reactor is in
Start
Stop
Terminate
Publish
Subscribe
Unsubscribe


Stopping
=========

A `stop` call puts the haka-mqtt reactor into a stop procedure:

1. Reactor enters ``stopping`` state.
2. ``MqttDisconnect`` is inserted into the preflight queue.
3. Place messages from the preflight queue in-flight until the
   ``MqttDisconnect`` is placed in the air.
4. Close socket writes.
5. Process messages on input until the remote closes its write stream
   and there is no more data left to read.
6. Enter ``stopped`` state.


Start
------

While in the ``stopping`` state calls to start have no effect.


Stop
-----

While in the ``stopping`` state calls to stop have no further effect.


Terminate
----------

While in the ``stopping`` calls to terminate function normally;
resources will be promptly cleaned up and the reactor will enter the
``stopped`` state before `terminate` returns.


Subscribe/Unsubscribe
----------------------

Calls made to subscribe/unsubscribe made prior to a ``stop`` call will
have their associated packets delivered to the server before the reactor
enters its ``mute`` state.  Callbacks to ``on_suback`` and
``on_unsuback`` will only be made for whatever acks are received prior
to the reactor entering a final state.  Calls to subscribe/unsubscribe
made after a ``stop`` call place packets on the preflight queue but
these packets will not be delivered before the reactor enters ``mute``
state and the packets will eventually be discarded if the reactor is
restarted after entering a final state.


Publish
--------

Calls to publish ``stopping`` state will add ``MqttPublish`` packets to
the pre-flight queue but these packets will not be delivered to the
server before a disconnect.  A successfull reconnection beginning with
a call to start will see them subseuqently delivered.


Terminating
============

A ``terminate`` call prompty closes all haka-mqtt reactor resources and
places the reactor into a ``stopped`` state.  All schedule deadlines are
promptly cancelled.  All socket resources are promptly closed.  Any
asynchronous hostname lookups are cancelled.
