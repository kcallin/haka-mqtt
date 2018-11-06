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

Subscribe/Unsubscribe
----------------------

Subscribe/unsubscribe calls made before a call to ``stop`` will have
their associated packets delivered before the socket outgoing write
channel is closed.  Whether the packets are acknowledged on not depends
on server implementation.

Publish
--------

Calls made to publish before a call to ``stop`` will have the associated
packets delivered before the socket's outgoing write channel is closed.
The server may or may not acknowledge QoS=1 publishes before closing the
socket.  QoS=2 packets may be acknowledge with a ``pubrec`` packet but
the reactor will not acknowledge the ``pubrec`` packet with a ``pubrel``
since the outgoing socket stream would already have been closed.  Any
``pubrel`` packets qeued before the call to stop will be delivered
before the outgoing write channel is closed and may or may not be
acknowledged by the server with a ``pubcomp``.


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
