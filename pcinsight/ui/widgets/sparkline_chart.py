"""Lightweight sparkline chart painted with QPainter.

No new dependencies: the widget draws a single polyline over the available
width, auto-scales the vertical axis to the data range and shows the current
value beside the line. An empty history renders a centered ``—`` placeholder.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ...models import MetricSample


def _VALUE_ACCESSOR(sample: MetricSample) -> float:
    return sample.cpu_percent


class SparklineChart(QWidget):
    """Draw one metric as a lightweight time-based line chart."""

    def __init__(
        self,
        label: str,
        unit: str = "",
        accessor: Callable[[MetricSample], float] = _VALUE_ACCESSOR,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._unit = unit
        self._accessor = accessor
        self._points: list[tuple[datetime, float]] = []
        self._current: float | None = None
        self.setMinimumHeight(110)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self.update)
        self._refresh_timer.start()

    # ------------------------------------------------------------------ data

    def set_samples(self, samples: list[MetricSample]) -> None:
        """Replace the plotted samples with ``samples`` (oldest first)."""
        self._points = [(sample.timestamp, self._accessor(sample)) for sample in samples]
        if samples:
            self._current = self._accessor(samples[-1])
        else:
            self._current = None
        self.update()

    def set_current(self, value: float | None) -> None:
        self._current = value
        self.update()

    def set_accessor(self, accessor: Callable[[MetricSample], float]) -> None:
        """Update the value accessor function."""
        self._accessor = accessor

    # ---------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(34, 8, 8, 24)

        if not self._points:
            painter.setPen(QColor("#858b95"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "—")
            return

        values = [value for _, value in self._points]
        vmin = min(values)
        vmax = max(values)
        span = vmax - vmin if vmax != vmin else 1.0

        def to_y(value: float) -> float:
            return rect.bottom() - (value - vmin) / span * rect.height()

        step_x = rect.width() / max(1, len(self._points) - 1)

        # Gridlines / background track.
        painter.setPen(QPen(QColor("#2a2e35"), 1))
        for fraction in (0.25, 0.5, 0.75):
            y = rect.bottom() - fraction * rect.height()
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        # Polyline.
        path = QPainterPath()
        for index, (_, value) in enumerate(self._points):
            x = rect.left() + index * step_x
            y = to_y(value)
            if index == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        pen = QPen(QColor("#4c8dff"), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)

        # Points.
        painter.setBrush(QColor("#4c8dff"))
        for index, (_, value) in enumerate(self._points):
            x = rect.left() + index * step_x
            y = to_y(value)
            painter.drawEllipse(QPointF(x, y), 3, 3)

        # Axis labels.
        painter.setPen(QColor("#7d848e"))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(rect.left(), rect.top() - 6, f"{vmax:.1f}{self._unit}")
        painter.drawText(rect.left(), rect.bottom() + 14, f"{vmin:.1f}{self._unit}")
        painter.drawText(rect.right() - 40, rect.bottom() + 14, "now")

        # Current value badge.
        if self._current is not None:
            painter.setPen(QColor("#eef0f3"))
            painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            painter.drawText(rect.right() - 70, rect.top() + 10, f"{self._current:.1f}{self._unit}")
