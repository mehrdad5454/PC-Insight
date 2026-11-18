"""OS abstraction contract.

Only this package may contain operating-system specific code. Every other
module in PC Insight talks to the :class:`Platform` protocol.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from ..models import CommandResult, DiskHealth, MetricSample, SystemInfo


class Platform(Protocol):
    """Operations PC Insight needs from the host operating system."""

    name: str

    def is_administrator(self) -> bool:
        """Return True when the current process runs with full privileges."""

    def os_release(self) -> str:
        """Return a human-readable operating-system description."""

    def default_data_dir(self, app_name: str) -> Path:
        """Return the OS application data folder for ``app_name``."""

    def run_command(
        self,
        args: Sequence[str],
        timeout: float = 15.0,
        encoding: str = "utf-8",
    ) -> CommandResult:
        """Run a command and capture its output.

        Non-zero exit codes are returned in the result, not raised. Only a
        failure to start the process raises ``PlatformError``. ``encoding`` is
        the text encoding used by the child process.
        """

    def run_powershell(self, script: str, timeout: float = 30.0) -> CommandResult:
        """Run a PowerShell script and capture its output as UTF-8."""

    def read_registry_value(self, hive: str, key: str, name: str) -> str | None:
        """Read a registry value, or return None when it does not exist."""

    def system_info(self) -> SystemInfo:
        """Return static system information.

        Fields the operating system does not report must be ``None``. A section
        that cannot be read is explained in ``SystemInfo.limitations``; only a
        complete failure raises ``PlatformError``.
        """

    def disk_health(self) -> list[DiskHealth]:
        """Return the health of every physical disk.

        An empty list means the operating system reported no physical disks.
        """

    def metric_sample(self) -> MetricSample:
        """Return one live resource sample.

        Counters the operating system does not report fall back to ``0`` or
        ``""`` in the returned sample; only a failure to read the required
        readings raises ``PlatformError``.
        """