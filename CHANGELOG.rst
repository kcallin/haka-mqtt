0.3.0 (2018-ab-cd)
===================

New
----
#15: Support disabling Reactor.recv_idle_ping_period.
     https://github.com/kcallin/haka-mqtt/issues/15

Fix
----
#16: Keepalive scheduled while pingreq already active.

     Reactor schedules a keepalive when it writes to a socket with a
     pingreq packet already in-the-air.

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