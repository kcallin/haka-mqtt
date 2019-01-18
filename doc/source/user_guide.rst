===========
User Guide
===========

The `haka_mqtt` package is reliable "weapons grade" MQTT client library.
It contains a core mqtt reactor class built with provable reliability,
and reproducibility as its fundamental goals.  A side effect is that the
library turns out to be speedy as well.

The core reactor takes some time to plumb into an application event loop.
To make life easier for simple use cases `haka-mqtt` includes a number of
front-ends that speed implementation by making some reasonable
assumptions.  If these assumptions do not hold for application then it
best to use the core reactor directly.


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   quickstart
   core
   frontend
   examples
   build_doc
   semver
   requirements
   weapons_grade
