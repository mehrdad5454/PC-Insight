"""Floating desktop panel for live performance metrics.

A small, draggable window that stays on top and shows sparklines for CPU,
memory, disk and network activity. Consumes the shared sampler service.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...models import MetricSample
from ...services.sampler_service import SamplerService
from ._widgets import Card
from .sparkline_chart import SparklineChart


def _CPU_ACCESSOR(sample: MetricSample) -> float:
    return sample.cpu_percent
def _RAM_ACCESSOR(sample: MetricSample) -> float:
    return sample.memory_percent
def _DISK_ACCESSOR(sample: MetricSample) -> float:
    return (
    sample.disk_read_bytes + sample.disk_write_bytes
) / 1e6
def _NET_ACCESSOR(sample: MetricSample) -> float:
    return (
    sample.net_recv_bytes + sample.net_sent_bytes
) / 1e6


class FloatingPanel(QWidget):
    """A draggable, always-on-top panel showing live resource sparklines."""

    visibility_changed = Signal(bool)

    def __init__(
        self,
        sampler_service: SamplerService,
        parent: QWidget | None = None,
    ) -> None:
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(parent, flags)
        self._sampler_service = sampler_service
        self._dragging = False
        self._drag_offset = QPoint()
        self._visible = True

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(280, 220)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Title bar with context menu
        self._title_bar = QWidget(self)
        self._title_bar.setFixedHeight(24)
        self._title_bar.setObjectName("FloatingTitleBar")
        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(8, 0, 8, 0)
        title_layout.setSpacing(4)

        self._title_label = QLabel("PC Insight", self._title_bar)
        self._title_label.setObjectName("FloatingTitle")
        title_layout.addWidget(self._title_label)
        title_layout.addStretch(1)

        self._menu_button = QPushButton("≡", self._title_bar)
        self._menu_button.setObjectName("FloatingMenuButton")
        self._menu_button.setFixedSize(24, 24)
        self._menu_button.clicked.connect(self._show_menu)
        title_layout.addWidget(self._menu_button)

        layout.addWidget(self._title_bar)

        # Charts grid
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self._charts = {
            "cpu": self._make_chart_card("CPU", "%", _CPU_ACCESSOR),
            "ram": self._make_chart_card("RAM", "%", _RAM_ACCESSOR),
            "disk": self._make_chart_card("Disk", " MB/s", _DISK_ACCESSOR),
            "network": self._make_chart_card("Net", " MB/s", _NET_ACCESSOR),
        }
        positions = ((0, 0), (0, 1), (1, 0), (1, 1))
        for (_key, card), (row, col) in zip(self._charts.items(), positions, strict=False):
            grid.addWidget(card, row, col)
        layout.addLayout(grid, 1)

        # Context menu
        self._menu = QMenu(self)
        self._always_on_top_action = QAction("Always on Top", self, checkable=True)
        self._always_on_top_action.setChecked(True)
        self._always_on_top_action.toggled.connect(self._toggle_always_on_top)
        self._menu.addAction(self._always_on_top_action)

        self._hide_action = QAction("Hide Panel", self)
        self._hide_action.triggered.connect(self.hide_panel)
        self._menu.addAction(self._hide_action)

        # Connect to sampler service
        self._sampler_service.sampled.connect(self._on_sampled)
        self._apply_sample(self._sampler_service.history)

        # Periodic refresh for current values
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_current)
        self._refresh_timer.start()

    def _make_chart_card(
        self, title: str, unit: str, accessor: Callable[[MetricSample], float]
    ) -> QWidget:
        card = Card(title, parent=self)
        layout = card.layout()
        chart = SparklineChart(title, unit=unit, accessor=accessor, parent=card)
        layout.addWidget(chart)
        card._chart = chart
        return card

    def _apply_sample(self, samples: list[MetricSample]) -> None:
        for key, card in self._charts.items():
            chart: SparklineChart = card._chart  # type: ignore[attr-defined]
            accessor = {
                "cpu": _CPU_ACCESSOR,
                "ram": _RAM_ACCESSOR,
                "disk": _DISK_ACCESSOR,
                "network": _NET_ACCESSOR,
            }[key]
            chart.set_accessor(accessor)
            chart.set_samples(samples)

    def _on_sampled(self, sample: MetricSample) -> None:
        self._apply_sample(self._sampler_service.history)

    def _refresh_current(self) -> None:
        latest = self._sampler_service.latest
        if latest:
            for key, card in self._charts.items():
                chart: SparklineChart = card._chart  # type: ignore[attr-defined]
                accessor = {
                    "cpu": _CPU_ACCESSOR,
                    "ram": _RAM_ACCESSOR,
                    "disk": _DISK_ACCESSOR,
                    "network": _NET_ACCESSOR,
                }[key]
                chart.set_current(accessor(latest))

    def _show_menu(self) -> None:
        self._menu.exec(QCursor.pos())

    def _toggle_always_on_top(self, checked: bool) -> None:
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def hide_panel(self) -> None:
        self.hide()
        self._visible = False
        self._refresh_timer.stop()
        self.visibility_changed.emit(False)

    def show_panel(self) -> None:
        self.show()
        self._visible = True
        self._refresh_timer.start()
        self.visibility_changed.emit(True)

    def toggle_visibility(self) -> None:
        if self._visible:
            self.hide_panel()
        else:
            self.show_panel()

    def is_visible(self) -> bool:
        return self._visible

    # Mouse events for dragging
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._title_bar.underMouse():
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()

    def closeEvent(self, event) -> None:
        self._refresh_timer.stop()
        self._sampler_service.sampled.disconnect(self._on_sampled)
        super().closeEvent(event)