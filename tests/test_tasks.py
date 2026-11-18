"""Background task runner."""

from __future__ import annotations

import threading

import pytest

pytest.importorskip("PySide6")


def test_cancellation_token() -> None:
    from pcinsight.ui.tasks import CancellationToken

    token = CancellationToken()

    assert token.cancelled is False

    token.cancel()

    assert token.cancelled is True


def test_submit_returns_result(qt_app) -> None:
    from pcinsight.ui.tasks import TaskRunner

    runner = TaskRunner()
    received: dict[str, object] = {}

    runner.submit(lambda: 21 * 2, on_done=lambda r, e: received.update(result=r, error=e))

    assert runner.wait_for_done(2000)
    qt_app.processEvents()

    assert received == {"result": 42, "error": None}


def test_error_is_delivered(qt_app) -> None:
    from pcinsight.ui.tasks import TaskRunner

    runner = TaskRunner()
    received: dict[str, object] = {}

    def boom() -> None:
        raise ValueError("boom")

    runner.submit(boom, on_done=lambda r, e: received.update(result=r, error=e))

    assert runner.wait_for_done(2000)
    qt_app.processEvents()

    assert received["result"] is None
    assert isinstance(received["error"], ValueError)


def test_cooperative_cancellation(qt_app) -> None:
    from pcinsight.ui.tasks import TaskRunner

    runner = TaskRunner()
    started = threading.Event()
    release = threading.Event()
    received: dict[str, object] = {}

    def work(token) -> str:
        started.set()
        release.wait(2)
        return "cancelled" if token.cancelled else "done"

    token = runner.submit(
        work,
        with_token=True,
        on_done=lambda r, e: received.update(result=r, error=e),
    )
    assert started.wait(2)

    token.cancel()
    release.set()

    assert runner.wait_for_done(2000)
    qt_app.processEvents()

    assert received["result"] == "cancelled"