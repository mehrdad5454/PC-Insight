"""Collector wrappers around the Platform contract."""

from __future__ import annotations

from typing import Any

from pcinsight.collectors import disk_health, system_info
from pcinsight.errors import PlatformError
from pcinsight.models import CollectorStatus, DiskHealth, DiskInfo, SystemInfo


class FakePlatform:
    name = "windows"

    def __init__(
        self,
        *,
        info: SystemInfo | None = None,
        disks: list[DiskHealth] | None = None,
        info_error: Exception | None = None,
        disk_error: Exception | None = None,
    ) -> None:
        self._info = info
        self._disks = disks or []
        self._info_error = info_error
        self._disk_error = disk_error

    def system_info(self) -> SystemInfo:
        if self._info_error is not None:
            raise self._info_error
        if self._info is None:
            raise PlatformError("no system info configured")
        return self._info

    def disk_health(self) -> list[DiskHealth]:
        if self._disk_error is not None:
            raise self._disk_error
        return self._disks


def _info(**overrides: Any) -> SystemInfo:
    values: dict[str, Any] = {
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
    }
    values.update(overrides)
    return SystemInfo(**values)


def _disk(device: str = "0", friendly_name: str = "Test Disk") -> DiskHealth:
    return DiskHealth(device=device, friendly_name=friendly_name)


def test_system_info_collector_success() -> None:
    info = _info()
    result = system_info.collect(FakePlatform(info=info))

    assert result.name == "system_info"
    assert result.status is CollectorStatus.OK
    assert result.data is info
    assert result.message == ""
    assert result.duration_ms >= 0


def test_system_info_collector_partial() -> None:
    info = _info(limitations=["GPU information unavailable"])
    result = system_info.collect(FakePlatform(info=info))

    assert result.status is CollectorStatus.PARTIAL
    assert result.data is info
    assert "GPU information unavailable" in result.message


def test_system_info_collector_failed() -> None:
    result = system_info.collect(FakePlatform(info_error=PlatformError("query failed")))

    assert result.name == "system_info"
    assert result.status is CollectorStatus.FAILED
    assert result.message == "query failed"
    assert result.data is None


def test_system_info_collector_skipped() -> None:
    result = system_info.collect(
        FakePlatform(info_error=NotImplementedError("not supported"))
    )

    assert result.status is CollectorStatus.SKIPPED
    assert result.message == "not supported"


def test_system_info_collector_never_raises() -> None:
    result = system_info.collect(FakePlatform(info_error=RuntimeError("boom")))

    assert result.status is CollectorStatus.FAILED
    assert "boom" in result.message


def test_disk_health_collector_success() -> None:
    disks = [_disk("0", "Disk A"), _disk("1", "Disk B")]
    result = disk_health.collect(FakePlatform(disks=disks))

    assert result.name == "disk_health"
    assert result.status is CollectorStatus.OK
    assert result.data == disks
    assert result.duration_ms >= 0


def test_disk_health_collector_empty_is_partial() -> None:
    result = disk_health.collect(FakePlatform(disks=[]))

    assert result.status is CollectorStatus.PARTIAL
    assert result.data == []
    assert result.message == "No physical disks were reported"


def test_disk_health_collector_failed() -> None:
    result = disk_health.collect(
        FakePlatform(disk_error=PlatformError("access denied"))
    )

    assert result.status is CollectorStatus.FAILED
    assert result.message == "access denied"


def test_disk_health_collector_skipped() -> None:
    result = disk_health.collect(
        FakePlatform(disk_error=NotImplementedError("not supported"))
    )

    assert result.status is CollectorStatus.SKIPPED
    assert result.message == "not supported"


def test_disk_health_collector_never_raises() -> None:
    result = disk_health.collect(FakePlatform(disk_error=RuntimeError("boom")))

    assert result.status is CollectorStatus.FAILED
    assert "boom" in result.message


def test_system_info_collector_accepts_disk_info() -> None:
    info = _info(disks=[DiskInfo("C:", "", "NTFS", 100, 40, 60)])
    result = system_info.collect(FakePlatform(info=info))

    assert result.status is CollectorStatus.OK
    assert result.data is info