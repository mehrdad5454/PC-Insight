"""Application pages.

P4 adds the dashboard. The remaining MVP pages arrive in their own phases:

- ``dashboard.py`` — P4
- ``performance.py`` — P5
- ``storage.py`` — P6
- ``diagnostics.py`` — P7
- ``history.py`` — P8
"""

from .dashboard import DashboardPage
from .performance import PerformancePage

__all__ = ["DashboardPage", "PerformancePage"]