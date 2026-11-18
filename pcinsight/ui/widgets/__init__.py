"""Small reusable widgets shared by the pages.

Every widget is dumb: it takes already-computed values and paints them. No
widget collects data, starts work or builds SQL, so the pages stay the only
place that knows how the widgets fit together.
"""

from ._widgets import (
    Card,
    FieldRow,
    MetricBar,
    as_text,
    notice,
    section_title,
)
from .floating_panel import FloatingPanel
from .sparkline_chart import SparklineChart

__all__ = [
    "SparklineChart",
    "FloatingPanel",
    "Card",
    "MetricBar",
    "FieldRow",
    "section_title",
    "notice",
    "as_text",
]