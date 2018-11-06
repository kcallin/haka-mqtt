==================
Reactor Lifecycle
==================

A reactor has active and inactive states.  While in an inactive state
no sockets are active, no DNS calls are active, and no tasks are
scheduled.  Any of these may be true in an active state.

The normal reactor lifecycle is summarized in this state diagram:

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

        starting -> error [label="err"];
        started -> error [label="err"];
        stopping -> error [label="err"];
    }

Start
======

Calls to `start` can be used to activate an inactive reactor otherwise
they have no effect.


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


Stop
=====

Calls to `stop` may be used to at the earliest possible opportunity
cleanly disconnect from a server.

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

        "error" -> "error" [label="stop"];

        "stopped" -> "stopped" [label="stop"];
        "starting" -> "stopping" [label="stop"];
        "stopping" -> "stopping" [label="stop"];
    }


Terminate
==========

A ``terminate`` call prompty closes all haka-mqtt reactor resources and
places the reactor into a ``stopped`` state.  All schedule deadlines are
promptly cancelled.  All socket resources are promptly closed.  Any
asynchronous hostname lookups are cancelled.  "Prompt" in this case
means before the ``terminate`` call has returned.


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

        "init" -> "stopped" [label="terminate"];
        "starting" -> "stopped" [label="terminate"];
        "started" -> "stopped" [label="terminate"];
        "stopping" -> "stopped"  [label="terminate"];

        "error" -> "error" [label="terminate"];
    }


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
