"""Composition root and entry point for PC Insight."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from . import __version__
from .capabilities import detect
from .config import APP_NAME, resolve_paths
from .context import AppContext
from .logging_setup import setup_logging
from .models import Capabilities
from .platform import get_platform
from .platform.base import Platform
from .services.sampler_service import SamplerService
from .services.system_info import SystemInfoService
from .storage import db, repository

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="pc-insight",
        description=f"{APP_NAME} - local-first PC diagnostics for Windows 10/11",
    )
    parser.add_argument(
        "--portable",
        action="store_true",
        help="store data in a 'data' folder next to the application",
    )
    parser.add_argument("--debug", action="store_true", help="enable debug logging")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    return parser


def _fallback_capabilities(error: Exception) -> Capabilities:
    return Capabilities(
        platform="unknown",
        is_administrator=False,
        os_release="",
        limitations=[f"Capability detection failed: {error}"],
    )


def build_services(context: AppContext, platform: Platform | None = None) -> dict[str, Any]:
    """Create the services the UI needs for this run.

    A service that cannot start is logged and skipped instead of aborting the
    application: the window still opens and the page that needs it reports the
    missing capability. ``platform`` exists so tests can inject a stub.
    """
    services: dict[str, Any] = {}
    try:
        active = get_platform() if platform is None else platform
    except Exception as exc:
        logger.warning("metric sampling is unavailable: %s", exc)
        return services

    try:
        services["system_info"] = SystemInfoService(active)
    except Exception as exc:
        logger.warning("system information is unavailable: %s", exc)

    # Create the shared sampler service for P5 (periodic sampling for
    # Performance page and Floating panel)
    try:
        sampler_service = SamplerService(
            platform=active,
            db_path=context.paths.database,
            settings=context.settings,
            task_runner=None,  # Will be set by MainWindow
        )
        services["sampler_service"] = sampler_service
        context.sampler_service = sampler_service
    except Exception as exc:
        logger.warning("sampler service is unavailable: %s", exc)

    return services


def main(argv: list[str] | None = None) -> int:
    """Run the application and return a process exit code."""
    args = build_parser().parse_args(argv)

    if args.version:
        print(f"{APP_NAME} {__version__}")
        return 0

    paths = resolve_paths(portable=args.portable)
    logger = setup_logging(debug=args.debug, log_file=paths.log_file)
    logger.info("%s %s starting", APP_NAME, __version__)
    logger.info("data directory: %s", paths.data_dir)

    try:
        capabilities = detect()
    except Exception as exc:
        logger.warning("capability detection failed: %s", exc)
        capabilities = _fallback_capabilities(exc)

    try:
        conn = db.connect(paths.database)
        db.migrate(conn)
        settings = repository.get_settings(conn)
    except Exception:
        logger.exception("database initialisation failed")
        print(f"Cannot initialise the local database at {paths.database}", file=sys.stderr)
        return 1

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        logger.exception("PySide6 is not installed")
        print(
            "PySide6 is required to run PC Insight. Install the dependencies with:\n"
            '  .venv\\Scripts\\python.exe -m pip install -e ".[dev]"',
            file=sys.stderr,
        )
        return 2

    from .ui.main_window import MainWindow

    context = AppContext(
        paths=paths,
        settings=settings,
        capabilities=capabilities,
        connection=conn,
    )
    context.services.update(build_services(context))

    qt_app = QApplication([sys.argv[0]])
    qt_app.setApplicationName(APP_NAME)
    qt_app.setApplicationVersion(__version__)
    qt_app.aboutToQuit.connect(context.connection.close)

    window = MainWindow(context)
    window.show()
    logger.info("main window shown")
    window.refresh()
    return int(qt_app.exec())