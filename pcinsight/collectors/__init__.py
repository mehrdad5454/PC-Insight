"""Read-only data collectors.

Every collector is a small function that reads from the system and returns a
``CollectorResult``. Collectors never write to disk, never touch the network
and never raise for expected problems. A failure in one collector must not
stop the application.

Operating-system specific reads live in ``pcinsight/platform``; the collectors
here only adapt the platform result to the common envelope.

Modules are added per phase:

- ``system_info.py`` — P2
- ``disk_health.py`` — P2
- ``metrics.py`` — P3
- ``storage.py`` — P6
- ``event_logs.py`` — P7
- ``startup.py`` — P7
"""