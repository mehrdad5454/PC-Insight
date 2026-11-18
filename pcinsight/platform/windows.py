"""Windows implementation of the Platform contract."""

from __future__ import annotations

import base64
import ctypes
import os
import platform as _platform
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from ..errors import PlatformError
from ..models import CommandResult, DiskHealth, MetricSample, SystemInfo

try:
    import winreg
except ImportError:
    winreg = None

CREATE_NO_WINDOW = 0x08000000
_UTF8_PREFIX = (
    "$ProgressPreference = 'SilentlyContinue';\n"
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;\n"
)


def _hive(name: str) -> object:
    if winreg is None:
        raise PlatformError("the Windows registry is not available on this platform")
    hives = {
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKCR": winreg.HKEY_CLASSES_ROOT,
        "HKU": winreg.HKEY_USERS,
        "HKCC": winreg.HKEY_CURRENT_CONFIG,
    }
    hive = hives.get(name.upper())
    if hive is None:
        raise PlatformError(f"unknown registry hive: {name!r}")
    return hive


def _to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class WindowsPlatform:
    """Windows 10/11 adapter."""

    name = "windows"

    def is_administrator(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def os_release(self) -> str:
        try:
            return f"{_platform.system()} {_platform.release()} ({_platform.version()})"
        except Exception:
            return _platform.system() or "unknown"

    def default_data_dir(self, app_name: str) -> Path:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / app_name

    def run_command(
        self,
        args: Sequence[str],
        timeout: float = 15.0,
        encoding: str = "utf-8",
    ) -> CommandResult:
        argv = [str(arg) for arg in args]
        if not argv:
            raise PlatformError("run_command requires at least one argument")

        kwargs: dict[str, object] = {
            "capture_output": True,
            "text": True,
            "encoding": encoding,
            "errors": "replace",
            "timeout": timeout,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = CREATE_NO_WINDOW

        started = time.perf_counter()
        try:
            completed = subprocess.run(argv, **kwargs)
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                returncode=-1,
                stdout=_to_text(exc.stdout),
                stderr=_to_text(exc.stderr),
                timed_out=True,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except (OSError, ValueError) as exc:
            raise PlatformError(f"cannot start {argv[0]!r}: {exc}") from exc

        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def run_powershell(self, script: str, timeout: float = 30.0) -> CommandResult:
        if sys.platform != "win32":
            raise PlatformError("PowerShell is only available on Windows")
        encoded = base64.b64encode((_UTF8_PREFIX + script).encode("utf-16-le")).decode("ascii")
        return self.run_command(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            timeout=timeout,
            encoding="utf-8",
        )

    def read_registry_value(self, hive: str, key: str, name: str) -> str | None:
        root = _hive(hive)
        try:
            with winreg.OpenKey(root, key) as handle:
                value, _ = winreg.QueryValueEx(handle, name)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise PlatformError(f"cannot read registry {hive}\\{key}\\{name}: {exc}") from exc
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    def system_info(self) -> SystemInfo:
        from ._windows_sysinfo import collect_system_info

        return collect_system_info(self)

    def disk_health(self) -> list[DiskHealth]:
        from ._windows_sysinfo import collect_disk_health

        return collect_disk_health(self)

    def metric_sample(self) -> MetricSample:
        from ._windows_metrics import collect_metric_sample

        return collect_metric_sample()