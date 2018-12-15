0.3.0 (2018-ab-cd)
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