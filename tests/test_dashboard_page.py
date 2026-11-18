"""Dashboard page rendering with collector results supplied by the caller."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel, QProgressBar  # noqa: E402

from pcinsight.config import AppPaths, Settings  # noqa: E402
from pcinsight.context import AppContext  # noqa: E402
from pcinsight.models import Capabilities, CollectorResult, DiskInfo, MetricSample  # noqa: E402
from pcinsight.ui.pages.dashboard import DashboardPage  # noqa: E402


def _context(tmp_path: Path, **service_overrides: object) -> AppContext:
    paths = AppPaths(
        data_dir=tmp_path,
        database=tmp_path / "pcinsight.db",
        logs_dir=tmp_path / "logs",
        log_file=tmp_path / "logs" / "pcinsight.log",
        cache_dir=tmp_path / "cache",
    )
    context = AppContext(
        paths=paths,
        settings=Settings(),
        capabilities=Capabilities(
            platform="windows",
            is_administrator=False,
            os_release="Windows 11",
            limitations=["Limited mode"],
        ),
        connection=sqlite3.connect(":memory:"),
    )
    context.services.update(service_overrides)
    return context


def _sample(**overrides: object) -> MetricSample:
    values: dict[str, object] = {
        "timestamp": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        "cpu_percent": 12.5,
        "memory_percent": 40.0,
        "memory_used_bytes": 4 * 1024**3,
        "disk_read_bytes": 2048,
        "disk_write_bytes": 1024,
        "net_recv_bytes": 512,
        "net_sent_bytes": 256,
        "top_process": "pcinsight.exe",
        "top_process_percent": 1.5,
    }
    values.update(overrides)
    return MetricSample(**values)  # type: ignore[arg-type]


def _info(**overrides: object) -> object:
    from pcinsight.models import SystemInfo

    values: dict[str, object] = {
        "os_name": "Windows",
        "os_version": "11",
        "cpu_name": "Test CPU",
        "cpu_logical_cores": 8,
        "cpu_physical_cores": 4,
        "cpu_base_mhz": 3000.0,
        "ram_total_bytes": 16 * 1024**3,
        "motherboard": "Test Board",
        "bios_vendor": "Test BIOS",
        "bios_version": "1.0",
        "gpus": ["Test GPU"],
        "disks": [DiskInfo("C:", "", "NTFS", 500 * 1024**3, 300 * 1024**3, 200 * 1024**3)],
        "limitations": [],
    }
    values.update(overrides)
    return SystemInfo(**values)  # type: ignore[arg-type]


def _label(page: DashboardPage, object_name: str, text: str) -> QLabel:
    for child in page.findChildren(QLabel):
        if child.objectName() == object_name and text in child.text():
            return child
    raise AssertionError(f"no {object_name} label containing {text!r}")


def test_page_starts_with_unknown_values(qt_app, tmp_path: Path) -> None:
    page = DashboardPage(_context(tmp_path))
    page.show()
    qt_app.processEvents()

    card_values = page.findChildren(QLabel, "CardValue")
    assert [label.text() for label in card_values].count("—") >= 3
    page.close()


def test_page_renders_collected_values(qt_app, tmp_path: Path) -> None:
    page = DashboardPage(_context(tmp_path))
    page.show()
    qt_app.processEvents()

    view = page.refresh(_info(), _sample())

    assert view.cpu_percent == 12.5
    assert _label(page, "CardValue", "12.5%") is not None
    assert _label(page, "FieldValue", "Test CPU") is not None
    assert _label(page, "FieldValue", "4 physical / 8 logical") is not None
    page.close()


def test_page_shows_metric_counters_from_the_sample(qt_app, tmp_path: Path) -> None:
    page = DashboardPage(_context(tmp_path))
    page.show()
    qt_app.processEvents()

    page.refresh(_info(), _sample())

    assert _label(page, "FieldValue", "2.0 KB total") is not None
    assert _label(page, "FieldValue", "512 B total") is not None
    page.close()


def test_page_renders_storage_rows(qt_app, tmp_path: Path) -> None:
    page = DashboardPage(_context(tmp_path))
    page.show()
    qt_app.processEvents()

    page.refresh(_info(), _sample())

    bars = page.findChildren(QProgressBar)
    assert len(bars) == 1
    assert bars[0].value() == 60
    page.close()


def test_page_reports_missing_disks_without_faking_them(qt_app, tmp_path: Path) -> None:
    page = DashboardPage(_context(tmp_path))
    page.show()
    qt_app.processEvents()

    page.refresh(_info(disks=[]), _sample())

    assert _label(page, "FieldValue", "No disk information was reported") is not None
    assert page.findChildren(QProgressBar) == []
    page.close()


def test_page_reports_a_failed_collection_as_unknown(qt_app, tmp_path: Path) -> None:
    page = DashboardPage(_context(tmp_path))
    page.show()
    qt_app.processEvents()

    page.refresh(None, None)

    assert _label(page, "FieldValue", "No disk information was reported") is not None
    assert _label(page, "CardValue", "—") is not None
    page.close()


def test_page_accepts_a_collector_result_payload(qt_app, tmp_path: Path) -> None:
    page = DashboardPage(_context(tmp_path))
    page.show()
    qt_app.processEvents()

    sample = _sample()
    payload = CollectorResult.success("metrics", data=sample)

    assert page.refresh(_info(), payload.data).cpu_percent == 12.5
    page.close()