"""Dashboard page: static system information plus one live metric sample.

The page renders whatever it is given through
:func:`pcinsight.ui.view_models.build_dashboard_view`. It never collects data
itself and never starts work: the window submits the collectors to the
``TaskRunner`` and hands the results here.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...context import AppContext
from .. import widgets
from ..view_models import MISSING, DashboardView, build_dashboard_view

_HARDWARE_FIELDS = (
    ("Processor", "cpu_name"),
    ("Cores", "cpu_cores"),
    ("Base frequency", "cpu_base_mhz"),
    ("Memory", "memory_total"),
    ("Motherboard", "motherboard"),
    ("BIOS", "bios"),
)

_COUNTER_FIELDS = (
    ("CPU", "cpu_percent"),
    ("Memory used", "memory_used"),
    ("Disk read", "disk_read"),
    ("Disk written", "disk_write"),
    ("Network received", "net_recv"),
    ("Network sent", "net_sent"),
)


class DashboardPage(QWidget):
    """Overview of the PC: hardware, current load and storage."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._view = build_dashboard_view(None, None)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        title = QLabel("Dashboard", self)
        title.setObjectName("PageTitle")
        outer.addWidget(title)

        subtitle = QLabel(f"Local database: {context.paths.database}", self)
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll, 1)

        body = QWidget(scroll)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)
        scroll.setWidget(body)

        self._cards = self._build_cards(body_layout)
        self._hardware_rows = self._build_fields(body_layout, "Hardware", _HARDWARE_FIELDS)
        self._storage_box = self._build_storage(body_layout)
        self._counter_rows = self._build_fields(body_layout, "Live counters", _COUNTER_FIELDS)
        self._gpu_box = self._build_gpu(body_layout)
        body_layout.addStretch(1)

        self.refresh(None, None)

    # ------------------------------------------------------------------ layout

    def _build_cards(self, layout: QVBoxLayout) -> dict[str, widgets.Card]:
        grid = QGridLayout()
        grid.setSpacing(12)
        cards = {
            "os": widgets.Card("Operating system", parent=self),
            "cpu": widgets.Card("CPU load", parent=self),
            "memory": widgets.Card("Memory", parent=self),
            "top_process": widgets.Card("Busiest process", parent=self),
        }
        for index, card in enumerate(cards.values()):
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        return cards

    def _build_fields(
        self, layout: QVBoxLayout, title: str, fields: tuple[tuple[str, str], ...]
    ) -> dict[str, widgets.FieldRow]:
        layout.addWidget(widgets.section_title(title, self))
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        rows: dict[str, widgets.FieldRow] = {}
        for index, (label, _key) in enumerate(fields):
            row = widgets.FieldRow(label, parent=self)
            rows[label] = row
            grid.addWidget(row, index // 2, (index % 2) * 2)
        layout.addLayout(grid)
        return rows

    def _build_storage(self, layout: QVBoxLayout) -> QVBoxLayout:
        layout.addWidget(widgets.section_title("Storage", self))
        box = QVBoxLayout()
        box.setSpacing(8)
        layout.addLayout(box)
        return box

    def _build_gpu(self, layout: QVBoxLayout) -> QVBoxLayout:
        layout.addWidget(widgets.section_title("Graphics", self))
        box = QVBoxLayout()
        box.setSpacing(2)
        layout.addLayout(box)
        return box

    # ------------------------------------------------------------- data update

    def refresh(self, info: Any, sample: Any) -> DashboardView:
        """Render the given collector results and return the view that was shown."""
        view = build_dashboard_view(info, sample)
        self._view = view

        os_value = (
            view.os_name
            if view.os_version == MISSING
            else f"{view.os_name} {view.os_version}"
        )
        self._cards["os"].set_value(os_value)
        self._cards["os"].set_hint(view.cpu_name)
        self._cards["cpu"].set_value(widgets.as_text(view.cpu_percent, unit="%"))
        self._cards["cpu"].set_hint(
            f"sampled at {view.sample_time}" if view.sample_time != MISSING else "not collected"
        )
        memory_hint = (
            f"{view.memory_used} of {view.memory_total}"
            if view.memory_total != MISSING
            else view.memory_used
        )
        self._cards["memory"].set_value(widgets.as_text(view.memory_percent, unit="%"))
        self._cards["memory"].set_hint(memory_hint)
        self._cards["top_process"].set_value(view.top_process)
        self._cards["top_process"].set_hint(
            f"{widgets.as_text(view.top_process_percent, unit='%')} CPU"
            if view.top_process_percent is not None
            else "not collected"
        )

        for label, row in self._hardware_rows.items():
            row.set_value(self._hardware_value(label, view))
        for label, row in self._counter_rows.items():
            row.set_value(self._counter_value(label, view))

        self._rebuild(self._storage_box, self._build_disk_widgets(view))
        self._rebuild(self._gpu_box, self._build_gpu_widgets(view))
        return view

    def _hardware_value(self, label: str, view: DashboardView) -> str:
        mapping = {
            "Processor": view.cpu_name,
            "Cores": view.cpu_cores,
            "Base frequency": view.cpu_base_mhz,
            "Memory": view.memory_total,
            "Motherboard": view.motherboard,
            "BIOS": view.bios,
        }
        return mapping.get(label, MISSING)

    def _counter_value(self, label: str, view: DashboardView) -> str:
        totals = {
            "Disk read": view.disk_read,
            "Disk written": view.disk_write,
            "Network received": view.net_recv,
            "Network sent": view.net_sent,
        }
        if label == "CPU":
            return widgets.as_text(view.cpu_percent, unit="%")
        if label == "Memory used":
            return view.memory_used
        total = totals.get(label, MISSING)
        return MISSING if total == MISSING else f"{total} total"

    def _build_disk_widgets(self, view: DashboardView) -> list[QWidget]:
        if not view.disks:
            return [widgets.FieldRow("Disks", "No disk information was reported", self)]
        built: list[QWidget] = []
        for disk in view.disks:
            heading = QLabel(f"{disk.title} · {disk.total_text}", self)
            heading.setObjectName("FieldValue")
            built.append(heading)
            bar = widgets.MetricBar("Used", self)
            bar.set_value(disk.used_percent, text=disk.used_text)
            built.append(bar)
            built.append(
                widgets.FieldRow(
                    "Free",
                    f"{disk.free_text} · {disk.health} · {disk.media_type}",
                    self,
                )
            )
        return built

    def _build_gpu_widgets(self, view: DashboardView) -> list[QWidget]:
        if not view.gpus:
            return [widgets.FieldRow("Graphics", "No graphics information was reported", self)]
        return [
            widgets.FieldRow(f"GPU {index + 1}", gpu, self)
            for index, gpu in enumerate(view.gpus)
        ]

    @staticmethod
    def _rebuild(box: QVBoxLayout, new_widgets: list[QWidget]) -> None:
        """Replace every widget in ``box`` with ``new_widgets``."""
        while box.count():
            item = box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for widget in new_widgets:
            box.addWidget(widget)

    def last_sample_time(self) -> str:
        """Return when the shown sample was collected, or ``—``."""
        return self._view.sample_time