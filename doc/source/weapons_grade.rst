"Weapons Grade"
===============

The `haka-mqtt` project was a response to a lack of reliability and
rigorous documentation in existing python MQTT clients at the time.
The authors were involved in projects that required thousands of
clients to operate for years without service in soft realtime
conditions over unreliable low-bandwith bandwidth data links.  There
was great desire to use off the shelf libraries but after two years of
trying it was decided that a new approach, `haka-mqtt`, was needed.

The new `haka-mqtt` library provides at its core a reactor built to be
thoroughly and deterministically tested.  Its memory usage is stable
and well documented.  It is built to use non-blocking sockets in a
select-type M:N thread model where M client tasks are mapped onto
N threads.  Where suitable non-blocking APIs are not available (DNS
lookups), those operations can be performed in separate thread-pools
so that the client can continue its non-blocking operation.

Due to persistent questions it is necessary to state that the project
should not be used in conjunction with enriched uranium, TNT, or any
form of cruise missile.

`haka`
-------

A primary purpose of software is to provide its authors the opportunity
to disguise elaborate puns as real work.  Eclipse's
`paho <https://www.eclipse.org/paho/>`_ project provides MQTT client
implementations and the verb "pāho"  means to broadcast or announce
(`Maori Dictionary
<http://www.maoridictionary.co.nz/index.cfm?dictionaryKeywords=pahomit>`_).
What then is a "weapon's grade announcement"?  The culturally ignorant
authors contend that the `haka
<https://www.youtube.com/watch?v=BI851yJUQQw>`_ dance performed by the
Maori is truly a weapons grade and announcement.  The authors are also
jealous and wish that they could participate.
