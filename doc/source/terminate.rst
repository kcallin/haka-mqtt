============
Terminating
============

A ``terminate`` call prompty closes all haka-mqtt reactor resources and
places the reactor into a ``stopped`` state.

All schedule dealines are cancelled.  All socket resources are closed.
Any asynchronous hostname lookups are cancelled.
