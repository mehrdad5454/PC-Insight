"""Floating desktop panel for live performance metrics.

A small, draggable window that stays on top and shows numerical values for CPU,
memory, disk and network activity. Consumes the shared sampler service.
"""

from __future__ import annotations

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
from ...ui.view_models import format_bytes, format_percent
from ._widgets import Card


class FloatingPanel(QWidget):
    """A draggable, always-on-top panel showing live resource values."""

    visibility_changed = Signal(bool)
    exit_requested = Signal()

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
        self.setFixedSize(280, 200)

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

        # Values grid
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self._cpu_card = self._make_value_card("CPU", "%")
        self._ram_card = self._make_value_card("RAM", "%")
        self._disk_card = self._make_value_card("Disk", "")
        self._net_card = self._make_value_card("Network", "")

        grid.addWidget(self._cpu_card, 0, 0)
        grid.addWidget(self._ram_card, 0, 1)
        grid.addWidget(self._disk_card, 1, 0)
        grid.addWidget(self._net_card, 1, 1)
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

        self._menu.addSeparator()

        self._exit_action = QAction("Exit Application", self)
        self._exit_action.triggered.connect(self.exit_requested.emit)
        self._menu.addAction(self._exit_action)

        # Connect to sampler service
        self._sampler_service.sampled.connect(self._on_sampled)
        self._apply_sample(self._sampler_service.history)

        # Periodic refresh for current values
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_current)
        self._refresh_timer.start()

    def _make_value_card(self, title: str, unit: str) -> Card:
        card = Card(title, "—", "", parent=self)
        card._value.setObjectName("FloatingCardValue")
        card._hint.setObjectName("FloatingCardHint")
        return card

    def _apply_sample(self, samples: list[MetricSample]) -> None:
        latest = samples[-1] if samples else None
        self._refresh_values(latest)

    def _refresh_values(self, sample: MetricSample | None) -> None:
        if sample is None:
            self._cpu_card.set_value("—")
            self._cpu_card.set_hint("")
            self._ram_card.set_value("—")
            self._ram_card.set_hint("")
            self._disk_card.set_value("—")
            self._disk_card.set_hint("")
            self._net_card.set_value("—")
            self._net_card.set_hint("")
            return

        # CPU: percentage
        self._cpu_card.set_value(format_percent(sample.cpu_percent))
        self._cpu_card.set_hint("Usage")

        # RAM: percentage and used/total
        ram_used = format_bytes(sample.memory_used_bytes)
        self._ram_card.set_value(format_percent(sample.memory_percent))
        self._ram_card.set_hint(f"{ram_used} used")

        # Disk: percentage and free space (need system info for total)
        # We only have read/write bytes in MetricSample, so show I/O rate
        disk_io = sample.disk_read_bytes + sample.disk_write_bytes
        self._disk_card.set_value(format_bytes(int(disk_io)) + "/s")
        self._disk_card.set_hint("I/O rate")

        # Network: download/upload speeds
        net_down = format_bytes(int(sample.net_recv_bytes)) + "/s"
        net_up = format_bytes(int(sample.net_sent_bytes)) + "/s"
        self._net_card.set_value(f"{net_down} ↓")
        self._net_card.set_hint(f"{net_up} ↑")

    def _on_sampled(self, sample: MetricSample) -> None:
        self._refresh_values(sample)

    def _refresh_current(self) -> None:
        latest = self._sampler_service.latest
        if latest:
            self._refresh_values(latest)

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