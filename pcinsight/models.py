"""Shared data contracts used by every PC Insight layer.

These models are intentionally dumb: no logic, no I/O and no Qt imports. They
are the stable boundary between collectors, services, storage and UI, so a
change inside one layer does not ripple into the others.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    """How much attention a finding deserves."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class CollectorStatus(StrEnum):
    """Outcome of a single collector run."""

    OK = "ok"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    FAILED = "failed"


class SafetyClass(StrEnum):
    """How safe it is to act on a reclaimable storage item.

    PC Insight only ever suggests; nothing in the MVP deletes files.
    """

    SAFE = "safe"
    REVIEW = "review"
    CAUTION = "caution"


@dataclass(slots=True)
class CommandResult:
    """Result of an external command or script."""

    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


@dataclass(slots=True)
class CollectorResult:
    """Uniform envelope returned by every collector.

    A collector never raises for expected problems: it returns a FAILED or
    SKIPPED result with a human-readable message instead.
    """

    name: str
    status: CollectorStatus
    data: Any = None
    message: str = ""
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.status is CollectorStatus.OK

    @classmethod
    def success(
        cls,
        name: str,
        data: Any = None,
        duration_ms: int = 0,
        message: str = "",
    ) -> CollectorResult:
        return cls(
            name=name,
            status=CollectorStatus.OK,
            data=data,
            message=message,
            duration_ms=duration_ms,
        )

    @classmethod
    def partial(
        cls,
        name: str,
        data: Any = None,
        duration_ms: int = 0,
        message: str = "",
    ) -> CollectorResult:
        return cls(
            name=name,
            status=CollectorStatus.PARTIAL,
            data=data,
            message=message,
            duration_ms=duration_ms,
        )

    @classmethod
    def skipped(cls, name: str, message: str, duration_ms: int = 0) -> CollectorResult:
        return cls(
            name=name,
            status=CollectorStatus.SKIPPED,
            message=message,
            duration_ms=duration_ms,
        )

    @classmethod
    def failed(cls, name: str, message: str, duration_ms: int = 0) -> CollectorResult:
        return cls(
            name=name,
            status=CollectorStatus.FAILED,
            message=message,
            duration_ms=duration_ms,
        )


@dataclass(slots=True)
class DiskInfo:
    """A single logical disk or partition."""

    device: str
    label: str
    filesystem: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    media_type: str = "unknown"
    health: str = "unknown"

    @property
    def free_percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return self.free_bytes / self.total_bytes * 100.0


@dataclass(slots=True)
class DiskHealth:
    """Health of one physical disk as reported by the storage stack."""

    device: str
    friendly_name: str
    media_type: str = "unknown"
    health_status: str = "unknown"
    operational_status: str = "unknown"


@dataclass(slots=True)
class SystemInfo:
    """Static hardware and operating-system description.

    A field is ``None`` when the operating system did not report it; no value is
    invented. ``limitations`` explains which sections could not be read.
    """

    os_name: str
    os_version: str
    cpu_name: str | None
    cpu_logical_cores: int | None
    cpu_physical_cores: int | None
    cpu_base_mhz: float | None
    ram_total_bytes: int | None
    motherboard: str | None
    bios_vendor: str | None
    bios_version: str | None
    gpus: list[str] = field(default_factory=list)
    disks: list[DiskInfo] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class MetricSample:
    """One point in the live resource history."""

    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_bytes: int
    disk_read_bytes: int = 0
    disk_write_bytes: int = 0
    net_recv_bytes: int = 0
    net_sent_bytes: int = 0
    top_process: str = ""
    top_process_percent: float = 0.0


@dataclass(slots=True)
class ScanItem:
    """A reclaimable storage candidate produced by the storage analysis."""

    path: str
    size_bytes: int
    category: str
    safety: SafetyClass
    confidence: float
    reason: str


@dataclass(slots=True)
class Finding:
    """A diagnostic result with a plain-language explanation."""

    rule_id: str
    severity: Severity
    title: str
    detail: str = ""
    recommendation: str = ""
    evidence: str = ""
    confidence: float = 1.0


@dataclass(slots=True)
class Capabilities:
    """What the current process is allowed to inspect."""

    platform: str
    is_administrator: bool
    os_release: str
    limitations: list[str] = field(default_factory=list)

    @property
    def has_full_access(self) -> bool:
        return self.is_administrator