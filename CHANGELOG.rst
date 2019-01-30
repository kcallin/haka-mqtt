===========
Change Log
===========


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