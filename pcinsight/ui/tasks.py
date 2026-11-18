"""Background task infrastructure.

A thin wrapper around ``QThreadPool``: every long-running job is cancellable,
and callbacks are delivered on the GUI thread so pages can update safely.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class TaskCancelled(Exception):
    """Raised when a task is cancelled before it starts."""


class CancellationToken:
    """Cooperative cancellation flag shared with a running task."""

    def __init__(self) -> None:
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True


class _Signals(QObject):
    """Marshal the completion callback onto the GUI thread."""

    done = Signal(object, object)

    def __init__(
        self,
        callback: Callable[[Any, Exception | None], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._callback = callback
        self.done.connect(self._deliver)

    def _deliver(self, result: Any, error: Exception | None) -> None:
        try:
            self._callback(result, error)
        finally:
            self.deleteLater()


class _Task(QRunnable):
    """Run a Python callable inside the pool."""

    def __init__(
        self,
        fn: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        token: CancellationToken,
        signals: _Signals,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._token = token
        self._signals = signals

    def run(self) -> None:
        if self._token.cancelled:
            self._signals.done.emit(None, TaskCancelled("task cancelled before start"))
            return
        try:
            result = self._fn(*self._args, **self._kwargs)
            error: Exception | None = None
        except Exception as exc:
            result = None
            error = exc
        self._signals.done.emit(result, error)


class TaskRunner:
    """Own a ``QThreadPool`` and the cancellation tokens of its jobs."""

    def __init__(self, parent: QObject | None = None) -> None:
        self._parent = parent
        self._pool = QThreadPool(parent)
        self._tokens: list[CancellationToken] = []
        self._signals: list[_Signals] = []

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        with_token: bool = False,
        on_done: Callable[[Any, Exception | None], None] | None = None,
        **kwargs: Any,
    ) -> CancellationToken:
        """Run ``fn`` in the pool and return its cancellation token.

        With ``with_token=True`` the token is passed as the first positional
        argument so a long-running callable can stop cooperatively.
        """

        def done(result: Any, error: Exception | None) -> None:
            with contextlib.suppress(ValueError):
                self._signals.remove(signals)
            with contextlib.suppress(ValueError):
                self._tokens.remove(token)
            if on_done is not None:
                on_done(result, error)

        token = CancellationToken()
        self._tokens.append(token)
        call_args = (token, *args) if with_token else args
        signals = _Signals(done, self._parent)
        self._signals.append(signals)
        self._pool.start(_Task(fn, call_args, kwargs, token, signals))
        return token

    def cancel_all(self) -> None:
        """Request cancellation of every submitted task."""
        for token in self._tokens:
            token.cancel()

    def wait_for_done(self, timeout_ms: int = 5000) -> bool:
        """Wait until all tasks finish, or until the timeout expires."""
        return self._pool.waitForDone(timeout_ms)