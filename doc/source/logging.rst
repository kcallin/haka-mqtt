========
Logging
========

By default `haka-mqtt` logs details of operational events to `haka` log
through the standard Python logging framework.  Alternatively custom
loggers can be provided, or logging disabled entirely.


Log Levels
===========

Notice of network failures and server protocol violations are logged
at the `WARNING` level.  Notice of normal operational events such as
sending or receiving publish messages, connects, or normal disconnects
are logged at the `INFO` level.  Traces of bytes sent/received on
network sockets is logged at `DEBUG` level.


Standard Python `logging` Module
=================================

By default `haka-mqtt` logs details of operational events to `haka` log
through the standard Python logging framework.  If a `str` is provided
to the core :class:`haka_mqtt.reactor.Reactor` log parameter then logs
will to written to the logger by that name instead.


Custom Logging
===============

If a `logging.Logger`-like class is provided to the core
:class:`haka_mqtt.reactor.Reactor` log parameter then the logger will be
used as-is without a call to the standard library `logging.getLogger`
method.


Disabling Logging
==================

Logging can be disabled entirely by setting the
:class:`haka_mqtt.reactor.Reactor` log parameter to `None`.
