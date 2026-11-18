"""Performance page: live charts for CPU, RAM, disk and network.

The page consumes the single shared sampling stream exposed by
:class:`pcinsight.services.sampler_service.SamplerService` and renders every
metric as a lightweight sparkline. It never collects data itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...models import MetricSample
from ...services.sampler_service import SamplerService
from .. import widgets
from ..view_models import format_bytes, format_percent, text_or_missing
from ..widgets.sparkline_chart import SparklineChart

_CPU_ACCESSOR = lambda sample: sample.cpu_percent  # noqa: E731
_RAM_ACCESSOR = lambda sample: sample.memory_percent  # noqa: E731
_DISK_ACCESSOR = lambda sample: (sample.disk_read_bytes + sample.disk_write_bytes) / 1e6  # noqa: E731
_NET_ACCESSOR = lambda sample: (sample.net_recv_bytes + sample.net_sent_bytes) / 1e6  # noqa: E731

_RANGE_CHOICES = (
    ("15 minutes", timedelta(minutes=15)),
    ("1 hour", timedelta(hours=1)),
    ("24 hours", timedelta(hours=24)),
)


def _filter_window(samples: list[MetricSample], window: timedelta) -> list[MetricSample]:
    if not samples:
        return []
    cutoff = datetime.now(UTC) - window
    return [sample for sample in samples if sample.timestamp >= cutoff]


class PerformancePage(QWidget):
    """Live performance charts for the shared sampling stream."""

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.context = context
        self._service: SamplerService | None = context.sampler_service

        self._range = _RANGE_CHOICES[2][1]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        title = QLabel("Performance", self)
        title.setObjectName("PageTitle")
        outer.addWidget(title)

        subtitle = QLabel("Live CPU, memory, disk and network activity.", self)
        subtitle.setObjectName("PageSubtitle")
        outer.addWidget(subtitle)

        # ------------------------------------------------------------------ toolbar
        toolbar = QHBoxLayout()
        range_label = QLabel("Time range", self)
        range_label.setObjectName("FieldLabel")
        toolbar.addWidget(range_label)
        self._range_combo = QComboBox(self)
        self._range_combo.addItems([name for name, _ in _RANGE_CHOICES])
        self._range_combo.setCurrentText("24 hours")
        self._range_combo.currentTextChanged.connect(self._on_range_changed)
        toolbar.addWidget(self._range_combo)
        toolbar.addStretch(1)
        self._pause_button = QPushButton("Pause", self)
        self._pause_button.setObjectName("Action")
        self._pause_button.setCheckable(True)
        self._pause_button.clicked.connect(self._on_pause_toggled)
        toolbar.addWidget(self._pause_button)
        outer.addLayout(toolbar)

        # ---------------------------------------------------------------- charts
        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self._charts = {
            "cpu": self._make_chart_card("CPU load", "%", _CPU_ACCESSOR),
            "ram": self._make_chart_card("Memory", "%", _RAM_ACCESSOR),
            "disk": self._make_chart_card("Disk activity", " MB/s", _DISK_ACCESSOR),
            "network": self._make_chart_card("Network", " MB/s", _NET_ACCESSOR),
        }
        positions = ((0, 0), (0, 1), (1, 0), (1, 1))
        for (_key, card), (row, col) in zip(self._charts.items(), positions, strict=False):
            grid.addWidget(card, row, col)
        outer.addLayout(grid, 1)

        # ---------------------------------------------------------------- values
        values = QGridLayout()
        values.setSpacing(12)
        values.setColumnStretch(1, 1)
        values.setColumnStretch(3, 1)
        self._value_rows: dict[str, widgets.FieldRow] = {}
        fields = (
            ("CPU", "cpu"),
            ("Memory", "ram"),
            ("Disk read/write", "disk"),
            ("Network in/out", "network"),
        )
        for index, (label, key) in enumerate(fields):
            row = widgets.FieldRow(label, text_or_missing("—"), self)
            self._value_rows[key] = row
            values.addWidget(row, index // 2, (index % 2) * 2)
        outer.addLayout(values)

        outer.addStretch(1)

        self._paused = False
        self._apply_sample(self._service.history if self._service else [])
        if self._service:
            self._service.sampled.connect(self._on_sampled)

    # ------------------------------------------------------------------ chart card

    def _make_chart_card(self, title: str, unit: str, accessor) -> QWidget:
        card = widgets.Card(title, parent=self)
        layout = card.layout()
        chart = SparklineChart(title, unit=unit, accessor=accessor, parent=card)
        layout.addWidget(chart)
        card._chart = chart
        return card

    # ---------------------------------------------------------------- updates

    def _apply_sample(self, samples: list[MetricSample]) -> None:
        windowed = _filter_window(samples, self._range)
        for key, card in self._charts.items():
            chart: widgets.SparklineChart = card._chart  # type: ignore[attr-defined]
            accessor = {
                "cpu": _CPU_ACCESSOR,
                "ram": _RAM_ACCESSOR,
                "disk": _DISK_ACCESSOR,
                "network": _NET_ACCESSOR,
            }[key]
            chart.set_accessor(accessor)
            chart.set_samples(windowed)

        latest = windowed[-1] if windowed else None
        self._refresh_values(latest)

    def _refresh_values(self, sample: MetricSample | None) -> None:
        if sample is None:
            for row in self._value_rows.values():
                row.set_value(text_or_missing("—"))
            return
        self._value_rows["cpu"].set_value(format_percent(sample.cpu_percent))
        self._value_rows["ram"].set_value(format_percent(sample.memory_percent))
        disk = sample.disk_read_bytes + sample.disk_write_bytes
        self._value_rows["disk"].set_value(format_bytes(int(disk)) + "/s")
        net = sample.net_recv_bytes + sample.net_sent_bytes
        self._value_rows["network"].set_value(format_bytes(int(net)) + "/s")

    def _on_sampled(self, sample: MetricSample) -> None:
        if self._paused:
            return
        history = self._service.history if self._service else []
        self._apply_sample(history)

    def _on_range_changed(self, text: str) -> None:
        for name, window in _RANGE_CHOICES:
            if text == name:
                self._range = window
                break
        if self._service:
            self._apply_sample(self._service.history)

    def _on_pause_toggled(self, checked: bool) -> None:
        self._paused = checked
        self._pause_button.setText("Resume" if checked else "Pause")
