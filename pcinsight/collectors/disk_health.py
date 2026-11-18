"""Collector for physical disk health."""

from __future__ import annotations

import logging
import time

from ..models import CollectorResult
from ..platform.base import Platform

logger = logging.getLogger(__name__)


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _message(exc: Exception) -> str:
    text = str(exc).strip()
    return text or type(exc).__name__


def collect(platform: Platform) -> CollectorResult:
    """Return physical disk health as a ``CollectorResult``."""
    started = time.perf_counter()
    try:
        disks = platform.disk_health()
    except NotImplementedError as exc:
        return CollectorResult.skipped("disk_health", _message(exc), _duration_ms(started))
    except Exception as exc:
        logger.warning("disk_health collection failed: %s", exc)
        return CollectorResult.failed("disk_health", _message(exc), _duration_ms(started))

    duration = _duration_ms(started)
    if not disks:
        return CollectorResult.partial(
            "disk_health",
            data=disks,
            message="No physical disks were reported",
            duration_ms=duration,
        )
    logger.debug("disk_health collected %d disks in %d ms", len(disks), duration)
    return CollectorResult.success("disk_health", data=disks, duration_ms=duration)