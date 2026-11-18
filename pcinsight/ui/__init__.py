"""PySide6 layer.

The UI imports ``models`` and ``services`` only. It never calls Windows APIs
directly and never builds SQL.

P1 ships the window shell; P4 adds the navigation rail, the theme and the
dashboard. The remaining MVP pages are added in P5 - P8:

- ``pages/dashboard.py`` — P4
- ``pages/performance.py`` — P5
- ``pages/storage.py`` — P6
- ``pages/diagnostics.py`` — P7
- ``pages/history.py`` — P8

``theme.py`` owns the light/dark colour tokens and the generated stylesheet.
``view_models.py`` turns collected data into display strings and imports no Qt,
so the exact text a page shows is testable on its own.
"""