"""Entry point and CLI."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import pcinsight.app as app_module
from pcinsight import __version__
from pcinsight.app import build_parser, build_services, main
from pcinsight.config import AppPaths, Settings
from pcinsight.context import AppContext
from pcinsight.errors import PlatformError
from pcinsight.models import Capabilities
from pcinsight.services.sampler_service import SamplerService


class StubPlatform:
    name = "windows"


def _context(tmp_path: Path) -> AppContext:
    paths = AppPaths(
        data_dir=tmp_path,
        database=tmp_path / "pcinsight.db",
        logs_dir=tmp_path / "logs",
        log_file=tmp_path / "logs" / "pcinsight.log",
        cache_dir=tmp_path / "cache",
    )
    return AppContext(
        paths=paths,
        settings=Settings(),
        capabilities=Capabilities(
            platform="windows",
            is_administrator=False,
            os_release="Windows 11",
        ),
        connection=sqlite3.connect(":memory:"),
    )


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])

    assert args.portable is False
    assert args.debug is False
    assert args.version is False


def test_parser_flags() -> None:
    args = build_parser().parse_args(["--portable", "--debug"])

    assert args.portable is True
    assert args.debug is True


def test_version_flag_prints(capsys) -> None:
    exit_code = main(["--version"])

    assert exit_code == 0
    assert __version__ in capsys.readouterr().out


def test_build_services_wires_sampler_service(tmp_path: Path) -> None:
    services = build_services(_context(tmp_path), platform=StubPlatform())

    assert isinstance(services["sampler_service"], SamplerService)


def test_build_services_skips_sampler_when_the_platform_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom() -> None:
        raise PlatformError("platform unavailable")

    monkeypatch.setattr(app_module, "get_platform", _boom)

    assert build_services(_context(tmp_path)) == {}