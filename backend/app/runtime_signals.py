from __future__ import annotations

from collections.abc import Callable

_scheduler_wake: Callable[[], None] | None = None


def register_scheduler_wake(callback: Callable[[], None]) -> None:
    global _scheduler_wake
    _scheduler_wake = callback


def wake_scheduler() -> None:
    if _scheduler_wake is not None:
        _scheduler_wake()
