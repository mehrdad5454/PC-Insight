"""Windows platform adapter."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pcinsight.errors import PlatformError
from pcinsight.models import MetricSample
from pcinsight.platform import get_platform
from pcinsight.platform.windows import WindowsPlatform

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only adapter")


def test_get_platform_is_cached() -> None:
    first = get_platform()

    assert first.name == "windows"
    assert get_platform() is first


def test_is_administrator_returns_bool() -> None:
    assert isinstance(WindowsPlatform().is_administrator(), bool)


def test_run_command_captures_output() -> None:
    result = get_platform().run_command(["cmd", "/c", "echo pc-insight"])

    assert result.ok
    assert "pc-insight" in result.stdout
    assert result.duration_ms >= 0


def test_run_command_reports_missing_executable() -> None:
    with pytest.raises(PlatformError):
        get_platform().run_command(["pc-insight-missing-executable-xyz"])


def test_run_powershell_returns_output() -> None:
    result = get_platform().run_powershell("'pc-insight'")

    assert result.ok, result.stderr
    assert "pc-insight" in result.stdout


def test_read_registry_value() -> None:
    value = WindowsPlatform().read_registry_value(
        "HKLM",
        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        "ProductName",
    )

    assert value is None or "Windows" in value


def test_read_registry_value_missing() -> None:
    value = WindowsPlatform().read_registry_value(
        "HKLM",
        r"SOFTWARE\PcInsight\DoesNotExist",
        "Nope",
    )

    assert value is None


def test_read_registry_value_rejects_unknown_hive() -> None:
    with pytest.raises(PlatformError):
        WindowsPlatform().read_registry_value("XXXX", "SOFTWARE", "Value")


def test_metric_sample_delegates_to_the_windows_metrics_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pcinsight.platform import _windows_metrics

    expected = MetricSample(
        timestamp=datetime.now(UTC),
        cpu_percent=1.0,
        memory_percent=2.0,
        memory_used_bytes=3,
    )
    monkeypatch.setattr(_windows_metrics, "collect_metric_sample", lambda: expected)

    assert WindowsPlatform().metric_sample() is expected


def test_default_data_dir_uses_localappdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\test\AppData\Local")

    path = WindowsPlatform().default_data_dir("PCInsight")

    assert path == Path(r"C:\Users\test\AppData\Local") / "PCInsight"


def test_run_powershell_preserves_non_ascii() -> None:
    text = "\u0633\u0644\u0627\u0645"

    result = get_platform().run_powershell("'" + text + "'")

    assert result.ok, result.stderr
    assert result.stdout.strip() == text