"""Windows implementation of static system information collection.

All operating-system specific reads live here. The public Platform methods in
``windows.py`` delegate to this module; collectors never see PowerShell or the
registry.
"""

from __future__ import annotations

import contextlib
import html
import json
import os
import re
import time
from typing import Any

from ..errors import PlatformError
from ..models import CommandResult, DiskHealth, DiskInfo, SystemInfo
from .base import Platform

_COMMAND_TIMEOUT_S = 8.0
_TIME_BUDGET_S = 20.0
_CLIXML_ERROR = re.compile(r'<S S="Error">(.*?)</S>', re.DOTALL)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    for item in _as_list(value):
        if isinstance(item, dict):
            return item
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result <= 0:
        return None
    return result


def _normalize_media_type(value: Any) -> str:
    text = (_text(value) or "unknown").lower()
    if text in {"", "unspecified", "unknown"}:
        return "unknown"
    return text


def _normalize_status(value: Any) -> str:
    return (_text(value) or "unknown").lower()


def _short(exc: Exception) -> str:
    text = str(exc).strip()
    return (text or type(exc).__name__)[:240]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _describe_failure(result: CommandResult) -> str:
    if result.timed_out:
        return "PowerShell query timed out"
    raw = (result.stderr or "").strip() or (result.stdout or "").strip()
    match = _CLIXML_ERROR.search(raw)
    if match:
        raw = match.group(1)
    text = html.unescape(raw).replace("_x000D_", " ").replace("_x000A_", " ").strip()
    if not text:
        text = f"PowerShell query failed with exit code {result.returncode}"
    lowered = text.lower()
    if "access to a cim resource" in lowered or "access is denied" in lowered:
        return (
            "Access to the requested information was denied; "
            "administrator rights may be required"
        )
    return text[:240]


def _run_json(platform: Platform, script: str, *, timeout: float = _COMMAND_TIMEOUT_S) -> Any:
    result = platform.run_powershell(script, timeout=timeout)
    if not result.ok:
        raise PlatformError(_describe_failure(result))
    text = (result.stdout or "").lstrip("\ufeff").strip()
    if not text:
        return None
    if "#< CLIXML" in text:
        raise PlatformError(_describe_failure(result))
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlatformError(f"PowerShell returned invalid JSON: {exc}") from exc


def _timeout(deadline: float) -> float:
    remaining = deadline - time.perf_counter()
    return max(0.1, min(_COMMAND_TIMEOUT_S, remaining))


def _expired(deadline: float, section: str, limitations: list[str]) -> bool:
    if deadline - time.perf_counter() > 0:
        return False
    limitations.append(f"{section} skipped: time budget exhausted")
    return True


def _join_text(*values: Any) -> str | None:
    parts: list[str] = []
    for value in values:
        text = _text(value)
        if text:
            parts.append(text)
    return " ".join(parts) or None


def _collect_os(platform: Platform) -> tuple[str, str, list[str]]:
    limitations: list[str] = []
    product: str | None = None
    display: str | None = None
    build: str | None = None
    ubr: str | None = None
    try:
        key = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        product = platform.read_registry_value("HKLM", key, "ProductName")
        display = platform.read_registry_value("HKLM", key, "DisplayVersion")
        build = platform.read_registry_value("HKLM", key, "CurrentBuild")
        ubr = platform.read_registry_value("HKLM", key, "UBR")
    except Exception as exc:
        limitations.append(f"OS registry details unavailable: {_short(exc)}")

    name = _text(product) or "unknown"
    if name == "unknown":
        with contextlib.suppress(Exception):
            name = _text(platform.os_release()) or "unknown"

    parts: list[str] = []
    display_text = _text(display)
    build_text = _text(build)
    ubr_text = _text(ubr)
    if display_text:
        parts.append(display_text)
    if build_text:
        parts.append(f"{build_text}.{ubr_text}" if ubr_text else build_text)
    version = " ".join(parts) or "unknown"
    if version == "unknown":
        with contextlib.suppress(Exception):
            version = _text(platform.os_release()) or "unknown"

    if name == "unknown":
        limitations.append("Operating-system name unavailable")
    if version == "unknown":
        limitations.append("Operating-system version unavailable")
    return name, version, limitations


def _collect_cpu(
    platform: Platform, deadline: float
) -> tuple[str | None, int | None, int | None, float | None, list[str]]:
    limitations: list[str] = []
    name: str | None = None
    logical: int | None = None
    physical: int | None = None
    mhz: float | None = None
    processors: list[dict[str, Any]] = []
    cim_ok = False

    script = (
        "Get-CimInstance Win32_Processor | "
        "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed | "
        "ConvertTo-Json -Compress"
    )
    with contextlib.suppress(Exception):
        data = _run_json(platform, script, timeout=_timeout(deadline))
        processors = [item for item in _as_list(data) if isinstance(item, dict)]
        cim_ok = True

    if cim_ok:
        names: list[str] = []
        logical_values: list[int] = []
        physical_values: list[int] = []
        mhz_values: list[float] = []
        for item in processors:
            item_name = _text(item.get("Name"))
            if item_name and item_name not in names:
                names.append(item_name)
            logical_value = _int(item.get("NumberOfLogicalProcessors"))
            if logical_value is not None and logical_value > 0:
                logical_values.append(logical_value)
            physical_value = _int(item.get("NumberOfCores"))
            if physical_value is not None and physical_value > 0:
                physical_values.append(physical_value)
            mhz_value = _float(item.get("MaxClockSpeed"))
            if mhz_value is not None:
                mhz_values.append(mhz_value)
        if names:
            name = " / ".join(names)
        if logical_values:
            logical = sum(logical_values)
        if physical_values:
            physical = sum(physical_values)
        if mhz_values:
            mhz = max(mhz_values)
        if len(processors) > 1 and (
            len(logical_values) != len(processors) or len(physical_values) != len(processors)
        ):
            limitations.append("CPU core count is incomplete across processors")

    if (name is None or mhz is None) and deadline - time.perf_counter() > 0:
        key = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        if name is None:
            with contextlib.suppress(Exception):
                name = _text(platform.read_registry_value("HKLM", key, "ProcessorNameString"))
        if mhz is None:
            with contextlib.suppress(Exception):
                mhz = _float(platform.read_registry_value("HKLM", key, "~MHz"))

    if logical is None:
        with contextlib.suppress(Exception):
            logical = os.cpu_count()

    if name is None and logical is None and physical is None and mhz is None:
        limitations.append("CPU information unavailable")
    else:
        if name is None:
            limitations.append("CPU name unavailable")
        if logical is None:
            limitations.append("CPU logical core count unavailable")
        if physical is None:
            limitations.append("CPU physical core count unavailable")
        if mhz is None:
            limitations.append("CPU base clock unavailable")
    if logical is not None and physical is not None and physical > logical:
        limitations.append("CPU physical core count exceeds logical core count")
    return name, logical, physical, mhz, limitations


def _collect_memory(platform: Platform, deadline: float) -> tuple[int | None, list[str]]:
    total: int | None = None
    script = (
        "Get-CimInstance Win32_ComputerSystem | "
        "Select-Object TotalPhysicalMemory | ConvertTo-Json -Compress"
    )
    with contextlib.suppress(Exception):
        data = _run_json(platform, script, timeout=_timeout(deadline))
        item = _first_dict(data)
        if item:
            total = _int(item.get("TotalPhysicalMemory"))
            if total is not None and total <= 0:
                total = None

    if total is None and deadline - time.perf_counter() > 0:
        fallback = (
            "Get-CimInstance Win32_PhysicalMemory | "
            "Measure-Object Capacity -Sum | Select-Object Sum | ConvertTo-Json -Compress"
        )
        with contextlib.suppress(Exception):
            data = _run_json(platform, fallback, timeout=_timeout(deadline))
            item = _first_dict(data)
            if item:
                candidate = _int(item.get("Sum"))
                if candidate is not None and candidate > 0:
                    total = candidate

    limitations: list[str] = []
    if total is None:
        limitations.append("RAM total size unavailable")
    return total, limitations


def _collect_board(
    platform: Platform, deadline: float
) -> tuple[str | None, str | None, str | None, list[str]]:
    motherboard: str | None = None
    bios_vendor: str | None = None
    bios_version: str | None = None
    with contextlib.suppress(Exception):
        key = r"HARDWARE\DESCRIPTION\System\BIOS"
        motherboard = _join_text(
            platform.read_registry_value("HKLM", key, "BaseBoardManufacturer"),
            platform.read_registry_value("HKLM", key, "BaseBoardProduct"),
        )
        bios_vendor = _text(platform.read_registry_value("HKLM", key, "BIOSVendor"))
        bios_version = _text(platform.read_registry_value("HKLM", key, "BIOSVersion"))

    if (motherboard is None or bios_vendor is None or bios_version is None) and (
        deadline - time.perf_counter() > 0
    ):
        if motherboard is None:
            with contextlib.suppress(Exception):
                data = _run_json(
                    platform,
                    "Get-CimInstance Win32_BaseBoard | "
                    "Select-Object Manufacturer,Product | ConvertTo-Json -Compress",
                    timeout=_timeout(deadline),
                )
                item = _first_dict(data)
                if item:
                    motherboard = _join_text(item.get("Manufacturer"), item.get("Product"))
        if bios_vendor is None or bios_version is None:
            with contextlib.suppress(Exception):
                data = _run_json(
                    platform,
                    "Get-CimInstance Win32_BIOS | "
                    "Select-Object Manufacturer,SMBIOSBIOSVersion | ConvertTo-Json -Compress",
                    timeout=_timeout(deadline),
                )
                item = _first_dict(data)
                if item:
                    if bios_vendor is None:
                        bios_vendor = _text(item.get("Manufacturer"))
                    if bios_version is None:
                        bios_version = _text(item.get("SMBIOSBIOSVersion"))

    limitations: list[str] = []
    if motherboard is None:
        limitations.append("Motherboard information unavailable")
    if bios_vendor is None:
        limitations.append("BIOS vendor unavailable")
    if bios_version is None:
        limitations.append("BIOS version unavailable")
    return motherboard, bios_vendor, bios_version, limitations


def _collect_gpus(platform: Platform, deadline: float) -> tuple[list[str], list[str]]:
    limitations: list[str] = []
    gpus: list[str] = []
    script = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object -ExpandProperty Name | ConvertTo-Json -Compress"
    )
    try:
        data = _run_json(platform, script, timeout=_timeout(deadline))
        for item in _as_list(data):
            name = _text(item)
            if name and name not in gpus:
                gpus.append(name)
    except Exception as exc:
        limitations.append(f"GPU information unavailable: {_short(exc)}")
    gpus.sort()
    return gpus, limitations


def _collect_logical_disks(
    platform: Platform, deadline: float
) -> tuple[list[DiskInfo], list[str]]:
    limitations: list[str] = []
    disks: list[DiskInfo] = []
    script = (
        'Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | '
        "Select-Object DeviceID,VolumeName,FileSystem,Size,FreeSpace | "
        "ConvertTo-Json -Compress"
    )
    try:
        data = _run_json(platform, script, timeout=_timeout(deadline))
        for item in _as_list(data):
            if not isinstance(item, dict):
                continue
            device = _text(item.get("DeviceID"))
            if device is None:
                continue
            total = _int(item.get("Size"))
            free = _int(item.get("FreeSpace"))
            if total is None or total <= 0 or free is None or free < 0 or free > total:
                limitations.append(f"Disk {device} size information unavailable")
                continue
            disks.append(
                DiskInfo(
                    device=device,
                    label=_text(item.get("VolumeName")) or "",
                    filesystem=_text(item.get("FileSystem")) or "",
                    total_bytes=total,
                    used_bytes=total - free,
                    free_bytes=free,
                )
            )
    except Exception as exc:
        limitations.append(f"Disk information unavailable: {_short(exc)}")
    disks.sort(key=lambda disk: disk.device)
    return disks, limitations


def _collect_physical_disks(
    platform: Platform, deadline: float
) -> tuple[list[dict[str, Any]], list[str]]:
    limitations: list[str] = []
    physical: list[dict[str, Any]] = []
    script = (
        "Get-PhysicalDisk | "
        "Select-Object DeviceId,FriendlyName,MediaType,HealthStatus,OperationalStatus | "
        "ConvertTo-Json -Compress"
    )
    try:
        data = _run_json(platform, script, timeout=_timeout(deadline))
        for item in _as_list(data):
            if not isinstance(item, dict):
                continue
            physical.append(
                {
                    "device": _text(item.get("DeviceId")) or "",
                    "friendly_name": _text(item.get("FriendlyName")) or "",
                    "media_type": _normalize_media_type(item.get("MediaType")),
                    "health_status": _normalize_status(item.get("HealthStatus")),
                    "operational_status": _normalize_status(item.get("OperationalStatus")),
                }
            )
    except Exception as exc:
        limitations.append(f"Disk health information unavailable: {_short(exc)}")
    return physical, limitations


def _collect_partitions(
    platform: Platform, deadline: float
) -> tuple[list[dict[str, Any]], list[str]]:
    limitations: list[str] = []
    partitions: list[dict[str, Any]] = []
    script = "Get-Partition | Select-Object DiskNumber,DriveLetter | ConvertTo-Json -Compress"
    try:
        data = _run_json(platform, script, timeout=_timeout(deadline))
        for item in _as_list(data):
            if not isinstance(item, dict):
                continue
            drive = _text(item.get("DriveLetter"))
            number = _int(item.get("DiskNumber"))
            if drive is None or number is None:
                continue
            partitions.append({"disk_number": number, "drive": drive.upper()})
    except Exception as exc:
        limitations.append(f"Disk partition mapping unavailable: {_short(exc)}")
    return partitions, limitations


def _collect_disk_models(
    platform: Platform, deadline: float
) -> tuple[list[dict[str, Any]], list[str]]:
    limitations: list[str] = []
    models: list[dict[str, Any]] = []
    script = "Get-Disk | Select-Object Number,FriendlyName | ConvertTo-Json -Compress"
    try:
        data = _run_json(platform, script, timeout=_timeout(deadline))
        for item in _as_list(data):
            if not isinstance(item, dict):
                continue
            number = _int(item.get("Number"))
            friendly = _text(item.get("FriendlyName"))
            if number is None or friendly is None:
                continue
            models.append({"number": number, "friendly_name": friendly})
    except Exception as exc:
        limitations.append(f"Disk model mapping unavailable: {_short(exc)}")
    return models, limitations


def _map_disk_details(
    disks: list[DiskInfo],
    partitions: list[dict[str, Any]],
    models: list[dict[str, Any]],
    physical: list[dict[str, Any]],
) -> None:
    model_by_number = {item["number"]: item["friendly_name"] for item in models}
    physical_by_name: dict[str, list[dict[str, Any]]] = {}
    for item in physical:
        physical_by_name.setdefault(item["friendly_name"], []).append(item)

    for partition in partitions:
        drive = str(partition["drive"]).upper()
        device = f"{drive}:"
        disk = next((item for item in disks if item.device.upper() == device), None)
        if disk is None:
            continue
        friendly = model_by_number.get(partition["disk_number"])
        if not friendly:
            continue
        matches = physical_by_name.get(friendly, [])
        if len(matches) != 1:
            continue
        match = matches[0]
        disk.media_type = match["media_type"]
        disk.health = match["health_status"]


def _device_number(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 1 << 30


def _to_disk_health(physical: list[dict[str, Any]]) -> list[DiskHealth]:
    records = [
        DiskHealth(
            device=item["device"],
            friendly_name=item["friendly_name"],
            media_type=item["media_type"],
            health_status=item["health_status"],
            operational_status=item["operational_status"],
        )
        for item in physical
    ]
    records.sort(key=lambda record: (_device_number(record.device), record.device))
    return records


def _has_data(info: SystemInfo) -> bool:
    if info.cpu_name or info.cpu_logical_cores or info.cpu_physical_cores or info.cpu_base_mhz:
        return True
    if info.ram_total_bytes:
        return True
    if info.motherboard or info.bios_vendor or info.bios_version:
        return True
    if info.gpus or info.disks:
        return True
    if info.os_name and info.os_name.lower() != "unknown":
        return True
    return bool(info.os_version and info.os_version.lower() != "unknown")


def collect_system_info(platform: Platform) -> SystemInfo:
    """Collect static system information from Windows."""
    started = time.perf_counter()
    deadline = started + _TIME_BUDGET_S
    limitations: list[str] = []

    os_name, os_version, os_limits = _collect_os(platform)
    limitations.extend(os_limits)

    if _expired(deadline, "CPU information", limitations):
        cpu_name: str | None = None
        cpu_logical: int | None = None
        cpu_physical: int | None = None
        cpu_mhz: float | None = None
    else:
        cpu_name, cpu_logical, cpu_physical, cpu_mhz, cpu_limits = _collect_cpu(
            platform, deadline
        )
        limitations.extend(cpu_limits)

    if _expired(deadline, "Memory information", limitations):
        ram_total: int | None = None
    else:
        ram_total, ram_limits = _collect_memory(platform, deadline)
        limitations.extend(ram_limits)

    if _expired(deadline, "Motherboard and BIOS information", limitations):
        motherboard: str | None = None
        bios_vendor: str | None = None
        bios_version: str | None = None
    else:
        motherboard, bios_vendor, bios_version, board_limits = _collect_board(
            platform, deadline
        )
        limitations.extend(board_limits)

    if _expired(deadline, "GPU information", limitations):
        gpus: list[str] = []
    else:
        gpus, gpu_limits = _collect_gpus(platform, deadline)
        limitations.extend(gpu_limits)

    if _expired(deadline, "Disk information", limitations):
        disks: list[DiskInfo] = []
    else:
        disks, disk_limits = _collect_logical_disks(platform, deadline)
        limitations.extend(disk_limits)

    if disks and not _expired(deadline, "Disk media type and health", limitations):
        physical, physical_limits = _collect_physical_disks(platform, deadline)
        limitations.extend(physical_limits)

        partitions: list[dict[str, Any]] = []
        if physical and not _expired(deadline, "Disk partition mapping", limitations):
            partitions, partition_limits = _collect_partitions(platform, deadline)
            limitations.extend(partition_limits)

        models: list[dict[str, Any]] = []
        if partitions and not _expired(deadline, "Disk model mapping", limitations):
            models, model_limits = _collect_disk_models(platform, deadline)
            limitations.extend(model_limits)

        _map_disk_details(disks, partitions, models, physical)

        if disks and not physical and not physical_limits:
            limitations.append("Disk media type and health unavailable")

    info = SystemInfo(
        os_name=os_name,
        os_version=os_version,
        cpu_name=cpu_name,
        cpu_logical_cores=cpu_logical,
        cpu_physical_cores=cpu_physical,
        cpu_base_mhz=cpu_mhz,
        ram_total_bytes=ram_total,
        motherboard=motherboard,
        bios_vendor=bios_vendor,
        bios_version=bios_version,
        gpus=gpus,
        disks=disks,
        limitations=_dedupe(limitations),
    )

    if not _has_data(info):
        detail = "; ".join(info.limitations) or "no data was returned"
        raise PlatformError(f"No system information could be read: {detail}")
    return info


def collect_disk_health(platform: Platform) -> list[DiskHealth]:
    """Collect physical disk health from Windows."""
    started = time.perf_counter()
    deadline = started + _TIME_BUDGET_S
    physical, limitations = _collect_physical_disks(platform, deadline)
    if limitations:
        raise PlatformError("; ".join(limitations))
    return _to_disk_health(physical)