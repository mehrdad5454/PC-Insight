"""Collector orchestration.

Services are the layer the UI talks to. They own no data of their own: they run
collectors and hand back the ``CollectorResult`` envelopes, so a page never
imports a collector or a platform adapter.
"""

from __future__ import annotations

from ..collectors import system_info
from ..models import CollectorResult
from ..platform.base import Platform


class SystemInfoService:
    """Run the static system-information collector on demand."""

    def __init__(self, platform: Platform) -> None:
        self._platform = platform

    def collect(self) -> CollectorResult:
        """Return the collector result; the collector never raises."""
        return system_info.collect(self._platform)