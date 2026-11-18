"""UI formatting contracts: display strings with no window involved."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from pcinsight.models import DiskInfo
from pcinsight.ui.view_models import (
    MISSING,
    build_dashboard_view,
    format_bytes,
    format_count,
    format_duration_ms,
    format_mhz,
    format_percent,
    format_timestamp,
    text_or_missing,
)


def test_format_bytes_uses_binary_units() -> None:
    assert format_bytes(0) == "0 B"
    assert format_bytes(1023) == "1023 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1536) == "1.5 KB"
    assert format_bytes(5 * 1024**3) == "5.0 GB"
    assert format_bytes(None) == MISSING


def test_format_percent_and_mhz() -> None:
    assert format_percent(42.4) == "42%"
    assert format_percent(42.4, digits=1) == "42.4%"
    assert format_percent(None) == MISSING
    assert format_mhz(3200.0) == "3.20 GHz"
    assert format_mhz(800.0) == "800 MHz"
    assert format_mhz(None) == MISSING


def test_format_duration_and_timestamp() -> None:
    assert format_duration_ms(250) == "250 ms"
    assert format_duration_ms(1500) == "1.5 s"
    assert format_duration_ms(None) == MISSING
    assert format_timestamp(datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)) != MISSING
    assert format_timestamp(None) == MISSING


def test_format_count_and_text() -> None:
    assert format_count(1, singular="core") == "1 core"
    assert format_count(4, singular="core") == "4 cores"
    assert format_count(None, singular="core") == MISSING
    assert text_or_missing("  name  ") == "name"
    assert text_or_missing("") == MISSING
    assert text_or_missing(None) == MISSING


def _info(**overrides: object) -> SimpleNamespace:
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
        "disks": [DiskInfo("C:", "", "NTFS", 500, 200, 300)],
        "limitations": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _sample(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "timestamp": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        "cpu_percent": 12.5,
        "memory_percent": 40.0,
        "memory_used_bytes": 4096,
        "disk_read_bytes": 2048,
        "disk_write_bytes": 1024,
        "net_recv_bytes": 512,
        "net_sent_bytes": 256,
        "top_process": "pcinsight.exe",
        "top_process_percent": 1.5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_dashboard_view_formats_collected_values() -> None:
    view = build_dashboard_view(_info(), _sample())

    assert view.os_name == "Windows"
    assert view.cpu_name == "Test CPU"
    assert view.cpu_cores == "4 physical / 8 logical"
    assert view.cpu_base_mhz == "3.00 GHz"
    assert view.memory_total == "16.0 GB"
    assert view.cpu_percent == 12.5
    assert view.memory_percent == 40.0
    assert view.memory_used == "4.0 KB"
    assert view.top_process == "pcinsight.exe"
    assert view.top_process_percent == 1.5
    assert view.disk_read == "2.0 KB"
    assert view.sample_time != MISSING


def test_build_dashboard_view_reports_disk_usage() -> None:
    view = build_dashboard_view(_info(), _sample())

    disk = view.disks[0]
    assert disk.title == "C:"
    assert disk.used_percent == 40.0
    assert disk.used_text == "40%"
    assert disk.free_text == "300 B free"
    assert disk.total_text == "500 B"


def test_build_dashboard_view_without_a_sample_is_unknown_not_zero() -> None:
    view = build_dashboard_view(_info(), None)

    assert view.cpu_percent is None
    assert view.memory_percent is None
    assert view.memory_used == MISSING
    assert view.top_process == MISSING
    assert view.sample_time == MISSING
    assert view.disk_read == MISSING


def test_build_dashboard_view_without_collectors_reads_all_unknown() -> None:
    view = build_dashboard_view(None, None)

    assert view.os_name == MISSING
    assert view.cpu_name == MISSING
    assert view.cpu_cores == MISSING
    assert view.memory_total == MISSING
    assert view.disks == []
    assert view.gpus == []


def test_build_dashboard_view_flags_partial_information() -> None:
    view = build_dashboard_view(_info(gpus=[], limitations=["GPU unavailable"]), _sample())

    assert view.gpus == []
    assert view.limitations == ["GPU unavailable"]


def test_build_dashboard_view_handles_a_disk_of_unknown_size() -> None:
    info = _info(disks=[DiskInfo("D:", "Data", "NTFS", 0, 0, 0)])

    disk = build_dashboard_view(info, None).disks[0]

    assert disk.used_percent is None
    assert disk.used_text == MISSING
    assert disk.total_text == "0 B"