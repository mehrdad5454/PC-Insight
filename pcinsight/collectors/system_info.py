"""Collector for static system information."""

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
    """Return static system information as a ``CollectorResult``."""
    started = time.perf_counter()
    try:
        info = platform.system_info()
    except NotImplementedError as exc:
        return CollectorResult.skipped("system_info", _message(exc), _duration_ms(started))
    except Exception as exc:
        logger.warning("system_info collection failed: %s", exc)
        return CollectorResult.failed("system_info", _message(exc), _duration_ms(started))

    duration = _duration_ms(started)
    if info.limitations:
        message = "; ".join(info.limitations)
        logger.info("system_info collected with limitations: %s", message)
        return CollectorResult.partial(
            "system_info",
            data=info,
            message=message,
            duration_ms=duration,
        )
    logger.debug("system_info collected in %d ms", duration)
    return CollectorResult.success("system_info", data=info, duration_ms=duration)