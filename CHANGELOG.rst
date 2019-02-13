===========
Change Log
===========

0.3.5 (2019-02-12)
===================

New
----
#35: Added is_active method to core reactor.

     Determining whether a reactor had oustanding socket I/O, scheduler
     deadlines or futures was:

     if reactor.state in ACTIVE_STATES:
        pass  # Do stuff

     but this is less obvious than:

     if reactor.is_active():
        pass  # Do stuff

     The change should be helpful particularly to new users of the library.

     https://github.com/kcallin/haka-mqtt/issues/35

Fix
----
#27: MQTT 3.1.1, MQTT-2.3.1-1, Packet IDs must be non-zero.

     Packet ID generation starts at zero and this is a violation of
     MQTT 3.1.1 MQTT-2.3.1-1.  Packet IDs are now generated beginning
     with one instead of zero.

     https://github.com/kcallin/haka-mqtt/issues/27

#30: BlockingMqttClient must use BlockingSslSocketFactory for ssl.

     When uses incorrect socket factory when properties.ssl is an
     SSLContext BlockingMqttClient incorrectly uses a SslSocketFactory
     instead of a BlockingSslSocketFactory.

     https://github.com/kcallin/haka-mqtt/issues/30

#31: Log chosen DNS entry at INFO; others at DEBUG.

     On DNS lookup one entry is chosen as the endpoint and other
     entries are logged for information purposes.  This leads to noisy
     logs.  Chosen entry now logged at INFO and others are logged at
     DEBUG level.

     https://github.com/kcallin/haka-mqtt/issues/31

#32: DNS lookup of IP6 addresses logs address in square brackets.

     When logging IP6 addresses from DNS lookups the addresses should
     be enclosed by square brackets "[]" to distinguish them from port
     numbers.

     Before: 2001:db8:85a3:8d3:1319:8a2e:370:7348:443
     After: [2001:db8:85a3:8d3:1319:8a2e:370:7348]:443

     https://github.com/kcallin/haka-mqtt/issues/32

#34: MqttPingreq not always scheduled correctly.

     Client is not permitted to have more than one unacknowledged
     pingreq at any given time. When a keepalive pingreq comes due and
     the acknowledging pingresp is delayed (by say more than keepalive
     period) the reactor needs to be able to immediately launch a
     pingreq upon receipt of the pingresp.

     https://github.com/kcallin/haka-mqtt/issues/34


0.3.4 (2019-01-31)
===================

New
----
* BlockingMqttClient and MqttPollClient now support a SSLContext
  parameter.


Fix
----
#28: Assertion failure in __recv_idle_abort_timeout handler.

     If an recv_idle_abort_timeout occurs while the keepalive_timeout
     is active then an assertion fails resulting in a library crash.
     The assertion was incorrectly placed and has been removed.  Bug
     has existed since 0.3.0.

     https://github.com/kcallin/haka-mqtt/issues/28


0.3.3 (2019-01-29)
===================

Fix
----
#22: On p3k DNS async resolver does not pass bytes to write.

     On Python 3 the DNS async resolver passes str instead of bytes to
     an os.write call.  This results in a TypeError and crash.

     https://github.com/kcallin/haka-mqtt/issues/22

#24: On p3k HexOnStr __str__ method fails to return a str.

     On Python 3 str(HexOnStr) fails to return str and this results in
     a TypeError.

     https://github.com/kcallin/haka-mqtt/issues/24

#25: socket.timeout has None errno; fails assertion.

     When using reactor in blocking mode with timeouts, socket.timeout
     exceptions can be raised.  This is a subclass of socket.error
     and caught as such.  The reactor asserts that socket.error has
     meaningful errno so this crashes.

     https://github.com/kcallin/haka-mqtt/issues/25

#26: Poll frontends guarantee at least one read/write per poll call.

     When MqttPollClient/MqttBlockingClient were called, they should
     guarantee at least one read/write call per poll.  This way when
     the poll period is set to zero the read/write call will still be
     called (previously it might not be as clocks would timeout before
     the read/write call was made.

     https://github.com/kcallin/haka-mqtt/issues/26


0.3.2 (2019-01-13)
===================

Fix
----
#21: haka_mqtt/frontends/poll.py not included in build

     The polling frontend was mistakenly left out of the pypi package.

     https://github.com/kcallin/haka-mqtt/issues/21


0.3.1 (2018-12-30)
===================

New
----
#20: Remove ordering restrictions on QoS=2 send path.

     https://github.com/kcallin/haka-mqtt/issues/20

Fix
----
#17: Connect fail after DNS lookup fails to enter error state.

     After a DNS lookup succeeds but the subsequent socket connect fails
     core reactor may not enter the error state.

     https://github.com/kcallin/haka-mqtt/issues/17

#18: Haka crash when SSL raises socket.error with zero errno.

     Some SSL subsystems can raise socket.error exceptions with zero
     errno values.  This fails one of haka's assertions.  The assertion
     has been removed and the SocketReactorError class description has
     been changed.

     https://github.com/kcallin/haka-mqtt/issues/18

#19: Full socket buffer can trigger message retransmissions.

     When the socket buffer is full and a call to send returns with zero
     bytes then a second copy of the message may be queued in the
     reactor write buffer. The end result is that the message can be
     placed in flight more than once.

     https://github.com/kcallin/haka-mqtt/issues/19

0.3.0 (2018-12-17)
===================

It is recommended to update to update to 0.3.0 immediately to avoid a
crash as a result of #16.

New
----
#15: Support disabling Reactor.recv_idle_ping_period.
     https://github.com/kcallin/haka-mqtt/issues/15

Fix
----
#16: Keepalive scheduled while pingreq already active.

     If a write operation is triggered with a pingreq in-the-air then
     the reactor incorrectly schedules a new pingreq.  There is no
     danger of a new pingreq being launched but if a
     recv_idle_abort_timeout occurs while in this condition an assertion
     fails.

     This is a crashing bug.

     https://github.com/kcallin/haka-mqtt/issues/16


0.2.0 (2018-11-29)
===================

New
----
#9:  Run without keepalive.
     https://github.com/kcallin/haka-mqtt/issues/9

Fix
----
#13: trigger keepalive on send instead of recv.
     https://github.com/kcallin/haka-mqtt/issues/13


0.1.0 (2018-10-25)
===================
* Initial release.
