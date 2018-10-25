============
Terminating
============

A ``terminate`` call prompty closes all haka-mqtt reactor resources and
places the reactor into a ``stopped`` state.  All schedule deadlines are
promptly cancelled.  All socket resources are promptly closed.  Any
asynchronous hostname lookups are cancelled.
