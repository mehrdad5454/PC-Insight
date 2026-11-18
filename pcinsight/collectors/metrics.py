"""Collector for live resource metrics."""

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
    """Return one live metric sample as a ``CollectorResult``."""
    started = time.perf_counter()
    try:
        sample = platform.metric_sample()
    except NotImplementedError as exc:
        return CollectorResult.skipped("metrics", _message(exc), _duration_ms(started))
    except Exception as exc:
        logger.warning("metrics collection failed: %s", exc)
        return CollectorResult.failed("metrics", _message(exc), _duration_ms(started))

    duration = _duration_ms(started)
    logger.debug("metrics collected in %d ms", duration)
    return CollectorResult.success("metrics", data=sample, duration_ms=duration)