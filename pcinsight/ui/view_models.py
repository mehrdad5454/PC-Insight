"""Pure value formatting for the UI.

This module is the only place that turns collected data into display strings.
It imports no Qt and performs no I/O, so the exact output a page shows can be
tested without a running window.

Rules that apply everywhere:

- a value the operating system did not report becomes ``—``;
- a value that was collected but could not be read (collector ``FAILED`` or
  ``SKIPPED``) also becomes ``—``, never ``0``;
- percentages and sizes are rounded for reading, not for storing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

MISSING = "—"

_BYTES_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_bytes(count: int | None) -> str:
    """Return a size in binary units, or ``—`` when it is unknown."""
    if count is None:
        return MISSING
    value = float(count)
    negative = value < 0
    value = abs(value)
    for unit in _BYTES_UNITS:
        if value < 1024.0 or unit == _BYTES_UNITS[-1]:
            rendered = f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            return f"-{rendered}" if negative else rendered
        value /= 1024.0
    return MISSING


def format_percent(value: float | None, *, digits: int = 0) -> str:
    """Return a percentage, or ``—`` when it is unknown."""
    if value is None:
        return MISSING
    return f"{value:.{digits}f}%"


def format_mhz(value: float | None) -> str:
    """Return a CPU base frequency in GHz when it is known."""
    if value is None:
        return MISSING
    if value >= 1000.0:
        return f"{value / 1000.0:.2f} GHz"
    return f"{value:.0f} MHz"


def format_duration_ms(milliseconds: int | None) -> str:
    """Return a duration suitable for a hint line."""
    if milliseconds is None:
        return MISSING
    if milliseconds < 1000:
        return f"{milliseconds} ms"
    return f"{milliseconds / 1000.0:.1f} s"


def format_timestamp(value: datetime | None) -> str:
    """Return a local wall-clock timestamp, or ``—`` when there is none."""
    if value is None:
        return MISSING
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def format_count(value: int | None, *, singular: str, plural: str = "") -> str:
    """Return ``noun``/``nouns`` for a count, or ``—`` when it is unknown."""
    if value is None:
        return MISSING
    word = singular if value == 1 else (plural or f"{singular}s")
    return f"{value} {word}"


def text_or_missing(value: Any) -> str:
    """Return a non-empty string, or ``—`` when the value is missing."""
    if value is None:
        return MISSING
    text = str(value).strip()
    return text or MISSING


def _used_percent(total_bytes: int, free_bytes: int) -> float | None:
    """Return how much of a disk is used, or ``None`` when the size is unknown."""
    if total_bytes <= 0:
        return None
    used = total_bytes - free_bytes
    return max(0.0, min(100.0, used / total_bytes * 100.0))


@dataclass(frozen=True, slots=True)
class DiskRow:
    """One disk line in the storage card."""

    device: str
    title: str
    used_percent: float | None
    used_text: str
    free_text: str
    total_text: str
    health: str
    media_type: str


@dataclass(frozen=True, slots=True)
class DashboardView:
    """Every value the dashboard shows, already formatted."""

    os_name: str
    os_version: str
    cpu_name: str
    cpu_cores: str
    cpu_base_mhz: str
    memory_total: str
    motherboard: str
    bios: str
    gpus: list[str]
    disks: list[DiskRow]
    limitations: list[str]
    cpu_percent: float | None
    memory_percent: float | None
    memory_used: str
    disk_read: str
    disk_write: str
    net_recv: str
    net_sent: str
    top_process: str
    top_process_percent: float | None
    sample_time: str


def _cpu_cores(info: Any) -> str:
    """Return ``physical cores / logical processors`` with whatever is known."""
    physical = getattr(info, "cpu_physical_cores", None)
    logical = getattr(info, "cpu_logical_cores", None)
    if physical is not None and logical is not None:
        return f"{physical} physical / {logical} logical"
    if logical is not None:
        return format_count(logical, singular="logical processor")
    if physical is not None:
        return format_count(physical, singular="physical core")
    return MISSING


def _disk_rows(info: Any) -> list[DiskRow]:
    """Return one row per logical disk reported by ``SystemInfo``."""
    rows: list[DiskRow] = []
    for disk in getattr(info, "disks", []) or []:
        label = disk.label.strip() if disk.label else ""
        title = f"{disk.device} {label}".strip() or disk.device
        used = _used_percent(disk.total_bytes, disk.free_bytes)
        rows.append(
            DiskRow(
                device=disk.device,
                title=title,
                used_percent=used,
                used_text=format_percent(used),
                free_text=f"{format_bytes(disk.free_bytes)} free",
                total_text=format_bytes(disk.total_bytes),
                health=text_or_missing(disk.health),
                media_type=text_or_missing(disk.media_type),
            )
        )
    return rows


def build_dashboard_view(info: Any, sample: Any) -> DashboardView:
    """Combine static system information with one live sample.

    ``info`` and ``sample`` may be ``None`` when their collector failed; every
    field that depends on them then reads as unknown instead of showing a
    fabricated default.
    """
    os_name = text_or_missing(getattr(info, "os_name", None))
    os_version = text_or_missing(getattr(info, "os_version", None))
    cpu_name = text_or_missing(getattr(info, "cpu_name", None))
    memory_total_bytes = getattr(info, "ram_total_bytes", None)
    bios_vendor = text_or_missing(getattr(info, "bios_vendor", None))
    bios_version = text_or_missing(getattr(info, "bios_version", None))
    bios = (
        f"{bios_vendor} {bios_version}".strip()
        if bios_vendor != MISSING or bios_version != MISSING
        else MISSING
    )

    gpus = [str(gpu) for gpu in (getattr(info, "gpus", []) or [])]
    limitations = [str(item) for item in (getattr(info, "limitations", []) or [])]

    cpu_percent = getattr(sample, "cpu_percent", None)
    memory_percent = getattr(sample, "memory_percent", None)
    memory_used_bytes = getattr(sample, "memory_used_bytes", None)
    top_percent = getattr(sample, "top_process_percent", None)
    top_process = text_or_missing(getattr(sample, "top_process", None))

    return DashboardView(
        os_name=os_name,
        os_version=os_version,
        cpu_name=cpu_name,
        cpu_cores=_cpu_cores(info) if info is not None else MISSING,
        cpu_base_mhz=format_mhz(getattr(info, "cpu_base_mhz", None)),
        memory_total=format_bytes(memory_total_bytes),
        motherboard=text_or_missing(getattr(info, "motherboard", None)),
        bios=bios,
        gpus=gpus,
        disks=_disk_rows(info) if info is not None else [],
        limitations=limitations,
        cpu_percent=float(cpu_percent) if cpu_percent is not None else None,
        memory_percent=float(memory_percent) if memory_percent is not None else None,
        memory_used=format_bytes(memory_used_bytes),
        disk_read=format_bytes(getattr(sample, "disk_read_bytes", None)),
        disk_write=format_bytes(getattr(sample, "disk_write_bytes", None)),
        net_recv=format_bytes(getattr(sample, "net_recv_bytes", None)),
        net_sent=format_bytes(getattr(sample, "net_sent_bytes", None)),
        top_process=top_process,
        top_process_percent=float(top_percent) if top_percent is not None else None,
        sample_time=format_timestamp(getattr(sample, "timestamp", None)),
    )