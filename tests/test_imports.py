"""Every module in the package must import cleanly."""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import pcinsight


def _module_names() -> list[str]:
    return [info.name for info in pkgutil.walk_packages(pcinsight.__path__, prefix="pcinsight.")]


def test_non_ui_modules_import() -> None:
    for name in _module_names():
        if name.startswith("pcinsight.ui"):
            continue
        importlib.import_module(name)


def test_ui_modules_import() -> None:
    pytest.importorskip("PySide6")
    for name in _module_names():
        if name.startswith("pcinsight.ui"):
            importlib.import_module(name)