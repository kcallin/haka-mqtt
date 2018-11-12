=============
Core Reactor
=============

The core MQTT Reactor is the backend behind all event loops.  It is
built to be used with blocking sockets or with non-blocking sockets.
It does not itself integrate with any event loop and it is the different
frontends that match the reactor with event loops and whatever special
rule processing is required for the given application.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   reactor_lifecycle
   send_path
   receive_path
   subscribe_path
   keepalive_path
