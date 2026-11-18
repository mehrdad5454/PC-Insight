"""Data contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from pcinsight.models import (
    CollectorResult,
    CollectorStatus,
    CommandResult,
    DiskHealth,
    MetricSample,
    SafetyClass,
    Severity,
    SystemInfo,
)


def test_enum_values() -> None:
    assert Severity.CRITICAL.value == "critical"
    assert CollectorStatus.SKIPPED.value == "skipped"
    assert SafetyClass.REVIEW.value == "review"


def test_command_result_ok() -> None:
    assert CommandResult(returncode=0).ok
    assert not CommandResult(returncode=1).ok
    assert not CommandResult(returncode=0, timed_out=True).ok


def test_collector_result_success() -> None:
    result = CollectorResult.success("cpu", data={"cores": 8}, duration_ms=5)

    assert result.status is CollectorStatus.OK
    assert result.ok
    assert result.data == {"cores": 8}
    assert result.duration_ms == 5


def test_collector_result_non_ok_states() -> None:
    skipped = CollectorResult.skipped("disk_health", "needs administrator")
    failed = CollectorResult.failed("event_log", "access denied", duration_ms=7)
    partial = CollectorResult.partial("storage", data=[1, 2], message="2 folders skipped")

    assert skipped.status is CollectorStatus.SKIPPED
    assert skipped.message == "needs administrator"
    assert failed.status is CollectorStatus.FAILED
    assert failed.duration_ms == 7
    assert partial.status is CollectorStatus.PARTIAL
    assert partial.data == [1, 2]
    assert not skipped.ok
    assert not failed.ok
    assert not partial.ok


def test_disk_health_defaults() -> None:
    health = DiskHealth(device="0", friendly_name="Test Disk")

    assert health.media_type == "unknown"
    assert health.health_status == "unknown"
    assert health.operational_status == "unknown"


def test_system_info_allows_missing_values() -> None:
    info = SystemInfo(
        os_name="Windows",
        os_version="11",
        cpu_name=None,
        cpu_logical_cores=None,
        cpu_physical_cores=None,
        cpu_base_mhz=None,
        ram_total_bytes=None,
        motherboard=None,
        bios_vendor=None,
        bios_version=None,
    )

    assert info.cpu_name is None
    assert info.cpu_logical_cores is None
    assert info.cpu_physical_cores is None
    assert info.cpu_base_mhz is None
    assert info.ram_total_bytes is None
    assert info.motherboard is None
    assert info.bios_vendor is None
    assert info.bios_version is None
    assert info.gpus == []
    assert info.disks == []
    assert info.limitations == []


def test_metric_sample_defaults() -> None:
    sample = MetricSample(
        timestamp=datetime.now(UTC),
        cpu_percent=1.0,
        memory_percent=2.0,
        memory_used_bytes=3,
    )

    assert sample.disk_read_bytes == 0
    assert sample.disk_write_bytes == 0
    assert sample.net_recv_bytes == 0
    assert sample.net_sent_bytes == 0
    assert sample.top_process == ""
    assert sample.top_process_percent == 0.0