"""Windows system information collection and its helpers."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from pcinsight.errors import PlatformError
from pcinsight.models import CommandResult, DiskInfo
from pcinsight.platform import _windows_sysinfo as ws

CPU = "Win32_Processor"
MEMORY = "Win32_ComputerSystem"
BOARD = "Win32_BaseBoard"
BIOS = "Win32_BIOS"
GPU = "Win32_VideoController"
LOGICAL = "Win32_LogicalDisk"
PARTITIONS = "Get-Partition"
MODELS = "Get-Disk"
PHYSICAL = "Get-PhysicalDisk"


def _ok(payload: Any) -> CommandResult:
    return CommandResult(returncode=0, stdout=json.dumps(payload), duration_ms=1)


def _ok_text(text: str) -> CommandResult:
    return CommandResult(returncode=0, stdout=text, duration_ms=1)


def _fail(message: str = "query failed") -> CommandResult:
    return CommandResult(returncode=1, stderr=message, duration_ms=1)


def _registry() -> dict[tuple[str, str, str], str]:
    os_key = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    bios_key = r"HARDWARE\DESCRIPTION\System\BIOS"
    cpu_key = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
    return {
        ("HKLM", os_key, "ProductName"): "Windows 11 Pro",
        ("HKLM", os_key, "DisplayVersion"): "23H2",
        ("HKLM", os_key, "CurrentBuild"): "22631",
        ("HKLM", os_key, "UBR"): "4890",
        ("HKLM", bios_key, "BaseBoardManufacturer"): "Test Board Inc.",
        ("HKLM", bios_key, "BaseBoardProduct"): "TB-X1",
        ("HKLM", bios_key, "BIOSVendor"): "Test BIOS Inc.",
        ("HKLM", bios_key, "BIOSVersion"): "1.0",
        ("HKLM", cpu_key, "ProcessorNameString"): "Test CPU",
        ("HKLM", cpu_key, "~MHz"): "3000",
    }


def _scripts() -> dict[str, CommandResult]:
    return {
        CPU: _ok(
            {
                "Name": "Intel(R) Core(TM) i7-4770 CPU @ 3.40GHz",
                "NumberOfCores": 4,
                "NumberOfLogicalProcessors": 8,
                "MaxClockSpeed": 3401,
            }
        ),
        MEMORY: _ok({"TotalPhysicalMemory": 17116057600}),
        BOARD: _ok({"Manufacturer": "CIM Board", "Product": "CIM-X1"}),
        BIOS: _ok({"Manufacturer": "CIM BIOS", "SMBIOSBIOSVersion": "2.0"}),
        GPU: _ok_text('"Radeon RX 580 Series"'),
        LOGICAL: _ok(
            [
                {
                    "DeviceID": "C:",
                    "VolumeName": "",
                    "FileSystem": "NTFS",
                    "Size": 127451463680,
                    "FreeSpace": 19282784256,
                },
                {
                    "DeviceID": "D:",
                    "VolumeName": "New Volume",
                    "FileSystem": "NTFS",
                    "Size": 999815114752,
                    "FreeSpace": 928854495232,
                },
            ]
        ),
        PARTITIONS: _ok(
            [
                {"DiskNumber": 0, "DriveLetter": "C"},
                {"DiskNumber": 1, "DriveLetter": "D"},
                {"DiskNumber": 1, "DriveLetter": None},
            ]
        ),
        MODELS: _ok(
            [
                {"Number": 0, "FriendlyName": "OSC SSD 128GB"},
                {"Number": 1, "FriendlyName": "WDC WD20EURS-63SPKY0"},
            ]
        ),
        PHYSICAL: _ok(
            [
                {
                    "DeviceId": "0",
                    "FriendlyName": "OSC SSD 128GB",
                    "MediaType": "SSD",
                    "HealthStatus": "Healthy",
                    "OperationalStatus": "OK",
                },
                {
                    "DeviceId": "1",
                    "FriendlyName": "WDC WD20EURS-63SPKY0",
                    "MediaType": "Unspecified",
                    "HealthStatus": "Healthy",
                    "OperationalStatus": "OK",
                },
            ]
        ),
    }


class FakePlatform:
    name = "windows"

    def __init__(
        self,
        *,
        scripts: dict[str, CommandResult] | None = None,
        registry: dict[tuple[str, str, str], str] | None = None,
        admin: bool = False,
        os_release: str = "Windows 11 (10.0.22631)",
    ) -> None:
        self.scripts = scripts or {}
        self.registry = registry or {}
        self._admin = admin
        self._os_release = os_release

    def is_administrator(self) -> bool:
        return self._admin

    def os_release(self) -> str:
        return self._os_release

    def default_data_dir(self, app_name: str) -> Path:
        return Path("C:/data") / app_name

    def run_command(
        self,
        args: Sequence[str],
        timeout: float = 15.0,
        encoding: str = "utf-8",
    ) -> CommandResult:
        raise NotImplementedError

    def run_powershell(self, script: str, timeout: float = 30.0) -> CommandResult:
        for marker, result in self.scripts.items():
            if marker in script:
                return result
        return CommandResult(returncode=1, stderr="unexpected script", duration_ms=1)

    def read_registry_value(self, hive: str, key: str, name: str) -> str | None:
        return self.registry.get((hive, key, name))


def test_as_list() -> None:
    assert ws._as_list(None) == []
    assert ws._as_list({"a": 1}) == [{"a": 1}]
    assert ws._as_list([1, 2]) == [1, 2]
    assert ws._as_list("x") == ["x"]


def test_text_int_float() -> None:
    assert ws._text("  ") is None
    assert ws._text(" x ") == "x"
    assert ws._int("42") == 42
    assert ws._int(True) is None
    assert ws._int("bad") is None
    assert ws._float("3401") == 3401.0
    assert ws._float(0) is None
    assert ws._float("bad") is None


def test_normalize_values() -> None:
    assert ws._normalize_media_type("SSD") == "ssd"
    assert ws._normalize_media_type("Unspecified") == "unknown"
    assert ws._normalize_media_type(None) == "unknown"
    assert ws._normalize_status("Healthy") == "healthy"
    assert ws._normalize_status(None) == "unknown"


def test_describe_failure_handles_clixml() -> None:
    result = CommandResult(
        returncode=1,
        stderr=(
            '#< CLIXML\n<Objs Version="1.1.0.1">'
            '<S S="Error">Get-PhysicalDisk : Access to a CIM resource was not available '
            "to the client._x000D__x000A_</S></Objs>"
        ),
        duration_ms=1,
    )

    message = ws._describe_failure(result)

    assert "administrator" in message


def test_describe_failure_handles_timeout() -> None:
    result = CommandResult(returncode=-1, timed_out=True, duration_ms=1)

    assert "timed out" in ws._describe_failure(result)


def test_run_json_strips_bom() -> None:
    platform = FakePlatform(scripts={CPU: _ok_text('\ufeff{"Name": "CPU"}')})

    assert ws._run_json(platform, "Get-CimInstance Win32_Processor") == {"Name": "CPU"}


def test_run_json_rejects_invalid_json() -> None:
    platform = FakePlatform(scripts={CPU: _ok_text("not json")})

    with pytest.raises(PlatformError):
        ws._run_json(platform, "Get-CimInstance Win32_Processor")


def test_run_json_empty_output_is_none() -> None:
    platform = FakePlatform(scripts={CPU: _ok_text("")})

    assert ws._run_json(platform, "Get-CimInstance Win32_Processor") is None


def test_run_json_detects_clixml_on_success() -> None:
    platform = FakePlatform(scripts={CPU: _ok_text('#< CLIXML\n<S S="Error">denied</S>')})

    with pytest.raises(PlatformError, match="denied"):
        ws._run_json(platform, "Get-CimInstance Win32_Processor")


def test_collect_system_info_happy_path() -> None:
    platform = FakePlatform(scripts=_scripts(), registry=_registry())

    info = ws.collect_system_info(platform)

    assert info.os_name == "Windows 11 Pro"
    assert "23H2" in info.os_version
    assert "22631.4890" in info.os_version
    assert info.cpu_name == "Intel(R) Core(TM) i7-4770 CPU @ 3.40GHz"
    assert info.cpu_logical_cores == 8
    assert info.cpu_physical_cores == 4
    assert info.cpu_base_mhz == 3401.0
    assert info.ram_total_bytes == 17116057600
    assert info.motherboard == "Test Board Inc. TB-X1"
    assert info.bios_vendor == "Test BIOS Inc."
    assert info.bios_version == "1.0"
    assert info.gpus == ["Radeon RX 580 Series"]
    assert [disk.device for disk in info.disks] == ["C:", "D:"]

    first = info.disks[0]
    assert first.media_type == "ssd"
    assert first.health == "healthy"
    assert first.total_bytes == 127451463680
    assert first.used_bytes == 127451463680 - 19282784256
    assert first.free_bytes == 19282784256

    second = info.disks[1]
    assert second.media_type == "unknown"
    assert second.health == "healthy"
    assert second.label == "New Volume"

    assert info.limitations == []
    assert info.collected_at.tzinfo is not None


def test_collect_system_info_records_missing_sections() -> None:
    scripts = _scripts()
    scripts[CPU] = _fail()
    scripts[MEMORY] = _fail()
    scripts[GPU] = _fail()
    scripts[LOGICAL] = _fail()
    platform = FakePlatform(scripts=scripts, registry=_registry())

    info = ws.collect_system_info(platform)

    assert info.cpu_name == "Test CPU"
    assert info.cpu_base_mhz == 3000.0
    assert info.cpu_physical_cores is None
    assert info.ram_total_bytes is None
    assert info.gpus == []
    assert info.disks == []
    assert any("CPU physical core count unavailable" in item for item in info.limitations)
    assert any("RAM total size unavailable" in item for item in info.limitations)
    assert any("GPU information unavailable" in item for item in info.limitations)
    assert any("Disk information unavailable" in item for item in info.limitations)


def test_collect_system_info_skips_invalid_disk_size() -> None:
    scripts = _scripts()
    scripts[LOGICAL] = _ok(
        [
            {
                "DeviceID": "C:",
                "VolumeName": "",
                "FileSystem": "NTFS",
                "Size": 0,
                "FreeSpace": 0,
            }
        ]
    )
    platform = FakePlatform(scripts=scripts, registry=_registry())

    info = ws.collect_system_info(platform)

    assert info.disks == []
    assert any("C: size information unavailable" in item for item in info.limitations)


def test_collect_system_info_respects_time_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws, "_TIME_BUDGET_S", 0.0)
    platform = FakePlatform(scripts=_scripts(), registry=_registry())

    info = ws.collect_system_info(platform)

    assert info.os_name == "Windows 11 Pro"
    assert info.cpu_name is None
    assert info.ram_total_bytes is None
    assert info.gpus == []
    assert info.disks == []
    assert any("time budget exhausted" in item for item in info.limitations)


def test_collect_system_info_raises_when_nothing_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ws.os, "cpu_count", lambda: None)
    platform = FakePlatform(scripts={}, registry={}, os_release="unknown")

    with pytest.raises(PlatformError):
        ws.collect_system_info(platform)


def test_collect_system_info_stops_querying_after_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ws, "_TIME_BUDGET_S", 0.05)

    class SlowPlatform(FakePlatform):
        def __init__(self) -> None:
            super().__init__(scripts=_scripts(), registry=_registry())
            self.calls: list[str] = []

        def run_powershell(self, script: str, timeout: float = 30.0) -> CommandResult:
            self.calls.append(script)
            time.sleep(0.1)
            return super().run_powershell(script, timeout=timeout)

    platform = SlowPlatform()
    info = ws.collect_system_info(platform)

    assert info.os_name == "Windows 11 Pro"
    assert len(platform.calls) == 1
    assert info.ram_total_bytes is None
    assert info.gpus == []
    assert info.disks == []
    assert any("time budget exhausted" in item for item in info.limitations)


def test_map_disk_details_leaves_ambiguous_mapping_unknown() -> None:
    disks = [DiskInfo("C:", "", "NTFS", 100, 40, 60)]
    partitions = [{"disk_number": 0, "drive": "C"}]
    models = [{"number": 0, "friendly_name": "Same Disk"}]
    physical = [
        {
            "device": "0",
            "friendly_name": "Same Disk",
            "media_type": "ssd",
            "health_status": "healthy",
            "operational_status": "ok",
        },
        {
            "device": "1",
            "friendly_name": "Same Disk",
            "media_type": "hdd",
            "health_status": "healthy",
            "operational_status": "ok",
        },
    ]

    ws._map_disk_details(disks, partitions, models, physical)

    assert disks[0].media_type == "unknown"
    assert disks[0].health == "unknown"


def test_map_disk_details_ignores_missing_partition() -> None:
    disks = [DiskInfo("C:", "", "NTFS", 100, 40, 60)]
    partitions: list[dict[str, Any]] = []
    models = [{"number": 0, "friendly_name": "Disk"}]
    physical = [
        {
            "device": "0",
            "friendly_name": "Disk",
            "media_type": "ssd",
            "health_status": "healthy",
            "operational_status": "ok",
        }
    ]

    ws._map_disk_details(disks, partitions, models, physical)

    assert disks[0].media_type == "unknown"
    assert disks[0].health == "unknown"


def test_collect_disk_health_happy_path() -> None:
    platform = FakePlatform(scripts=_scripts(), registry=_registry())

    disks = ws.collect_disk_health(platform)

    assert [disk.device for disk in disks] == ["0", "1"]
    assert disks[0].friendly_name == "OSC SSD 128GB"
    assert disks[0].media_type == "ssd"
    assert disks[0].health_status == "healthy"
    assert disks[0].operational_status == "ok"
    assert disks[1].media_type == "unknown"


def test_collect_disk_health_raises_on_query_failure() -> None:
    scripts = _scripts()
    scripts[PHYSICAL] = _fail("access denied")
    platform = FakePlatform(scripts=scripts, registry=_registry())

    with pytest.raises(PlatformError, match="access denied"):
        ws.collect_disk_health(platform)


def test_collect_disk_health_returns_empty_list() -> None:
    scripts = _scripts()
    scripts[PHYSICAL] = _ok([])
    platform = FakePlatform(scripts=scripts, registry=_registry())

    assert ws.collect_disk_health(platform) == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_windows_system_info_real() -> None:
    from pcinsight.platform.windows import WindowsPlatform

    info = WindowsPlatform().system_info()

    assert info.os_name
    assert info.os_version
    assert info.cpu_name is None or isinstance(info.cpu_name, str)
    assert info.cpu_logical_cores is None or info.cpu_logical_cores >= 1
    assert info.cpu_physical_cores is None or info.cpu_physical_cores >= 1
    assert info.cpu_base_mhz is None or info.cpu_base_mhz > 0
    assert info.ram_total_bytes is None or info.ram_total_bytes > 0
    assert isinstance(info.gpus, list)
    assert isinstance(info.disks, list)
    for disk in info.disks:
        assert disk.total_bytes > 0
        assert 0 <= disk.free_bytes <= disk.total_bytes
        assert disk.used_bytes == disk.total_bytes - disk.free_bytes
    assert info.collected_at.tzinfo is not None
    assert isinstance(info.limitations, list)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_windows_disk_health_real() -> None:
    from pcinsight.platform.windows import WindowsPlatform

    disks = WindowsPlatform().disk_health()

    assert isinstance(disks, list)
    assert disks
    for disk in disks:
        assert isinstance(disk.device, str)
        assert isinstance(disk.friendly_name, str)
        assert isinstance(disk.media_type, str)
        assert isinstance(disk.health_status, str)
        assert isinstance(disk.operational_status, str)