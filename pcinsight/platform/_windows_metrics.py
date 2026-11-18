"""Live metric sampling built on psutil.

This module is the only place that reads runtime counters. Everything else sees
:class:`~pcinsight.models.MetricSample`, so the sampling library stays an
implementation detail of the Windows adapter.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar

import psutil

from ..errors import PlatformError
from ..models import MetricSample

logger = logging.getLogger(__name__)

_CPU_SAMPLE_DELAY_S = 0.1
_PROCESS_SAMPLE_DELAY_S = 0.1

T = TypeVar("T")


def _non_negative_int(value: int | None) -> int:
    """Return a counter as a non-negative integer."""
    return max(0, value or 0)


def _try_optional(loader: Callable[[], T], label: str) -> T | None:
    """Return ``loader()`` or ``None`` when that counter is unavailable."""
    try:
        return loader()
    except (psutil.Error, OSError, RuntimeError) as exc:
        logger.warning("%s unavailable: %s", label, exc)
        return None


def _read_cpu_percent() -> float:
    """Return the CPU usage measured over a short interval.

    ``psutil.cpu_percent(interval=None)`` compares against the previous call, so
    the first call only establishes the baseline and the value read after the
    delay is the measurement.
    """
    try:
        psutil.cpu_percent(interval=None)
        time.sleep(_CPU_SAMPLE_DELAY_S)
        return psutil.cpu_percent(interval=None)
    except (psutil.Error, OSError) as exc:
        raise PlatformError(f"cannot read CPU usage: {exc}") from exc


def _read_memory() -> tuple[float, int]:
    """Return memory usage percent and used bytes."""
    try:
        memory = psutil.virtual_memory()
    except (psutil.Error, OSError) as exc:
        raise PlatformError(f"cannot read memory usage: {exc}") from exc
    return float(memory.percent), int(memory.used)


def _sample_processes() -> tuple[str, float]:
    """Return the name and CPU percent of the busiest process.

    Per-process CPU usage also needs two reads, so every process is sampled once,
    the list is given a short interval, and each process is read again. A
    process that exits in between is skipped rather than reported as a failure.

    The kernel idle process (pid 0) is left out: it reports accumulated idle
    time instead of a workload, and its percentage is far above every real
    process, so it would always be the "top" process.
    """
    measured: list[psutil.Process] = []
    for process in psutil.process_iter():
        if process.pid == 0:
            continue
        try:
            process.cpu_percent()
        except (psutil.Error, OSError):
            continue
        measured.append(process)

    if not measured:
        return "", 0.0

    time.sleep(_PROCESS_SAMPLE_DELAY_S)

    busiest_name = ""
    busiest_percent = 0.0
    for process in measured:
        try:
            percent = process.cpu_percent()
            name = process.name()
        except (psutil.Error, OSError):
            continue
        if not busiest_name or percent > busiest_percent:
            busiest_name = name
            busiest_percent = percent

    return busiest_name, max(0.0, busiest_percent)


def collect_metric_sample() -> MetricSample:
    """Collect one live resource sample.

    CPU and memory are required, so a failure there raises ``PlatformError``.
    Optional counters and the busiest process fall back to ``0``/``""`` so the
    sample still carries the readings that did work; nothing is invented.
    """
    cpu_percent = _read_cpu_percent()
    memory_percent, memory_used_bytes = _read_memory()
    disk = _try_optional(psutil.disk_io_counters, "disk counters")
    net = _try_optional(psutil.net_io_counters, "network counters")
    processes = _try_optional(_sample_processes, "process list")
    top_process, top_process_percent = processes if processes is not None else ("", 0.0)

    return MetricSample(
        timestamp=datetime.now(UTC),
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        memory_used_bytes=memory_used_bytes,
        disk_read_bytes=_non_negative_int(disk.read_bytes) if disk is not None else 0,
        disk_write_bytes=_non_negative_int(disk.write_bytes) if disk is not None else 0,
        net_recv_bytes=_non_negative_int(net.bytes_recv) if net is not None else 0,
        net_sent_bytes=_non_negative_int(net.bytes_sent) if net is not None else 0,
        top_process=top_process,
        top_process_percent=top_process_percent,
    )