"""Application logic: sampling, diagnostic rules and reports.

Services orchestrate collectors, apply rules and produce the objects the UI
renders. They never import from ``pcinsight.ui``.

Modules are added per phase:

- ``system_info.py`` — P4 (runs the P2 collector for the UI)
- ``sampler.py`` — P3
- ``diagnostics.py`` — P7
- ``reports.py`` — P8
"""