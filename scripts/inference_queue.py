"""A bounded, observable single-worker queue for local model operations."""

from __future__ import annotations

import threading
import time
from collections import deque


class QueueFullError(RuntimeError):
    pass


class QueueTimeoutError(RuntimeError):
    pass


class InferenceCancelledError(RuntimeError):
    pass


class InferenceQueue:
    def __init__(self, max_waiting: int = 5, wait_timeout: float = 180.0) -> None:
        self.max_waiting = max_waiting
        self.wait_timeout = wait_timeout
        self._condition = threading.Condition()
        self._active = False
        self._waiters: deque[int] = deque()
        self._next_ticket = 1
        self._entered_at: float | None = None

    def snapshot(self) -> dict:
        with self._condition:
            active_seconds = (
                round(time.monotonic() - self._entered_at, 2)
                if self._active and self._entered_at is not None
                else 0.0
            )
            return {
                "active": int(self._active),
                "waiting": len(self._waiters),
                "capacity": self.max_waiting,
                "active_seconds": active_seconds,
            }

    def position(self) -> int:
        with self._condition:
            return len(self._waiters) + 1 if self._active else 0

    def acquire(self, cancel_event: threading.Event | None = None) -> float:
        started = time.monotonic()
        with self._condition:
            ticket: int | None = None
            if self._active or self._waiters:
                if len(self._waiters) >= self.max_waiting:
                    raise QueueFullError("The local model queue is full")
                ticket = self._next_ticket
                self._next_ticket += 1
                self._waiters.append(ticket)
                try:
                    while self._active or self._waiters[0] != ticket:
                        if cancel_event and cancel_event.is_set():
                            raise InferenceCancelledError("Request cancelled while queued")
                        remaining = self.wait_timeout - (time.monotonic() - started)
                        if remaining <= 0:
                            raise QueueTimeoutError("Timed out waiting for the local model")
                        self._condition.wait(timeout=min(remaining, 0.5))
                except Exception:
                    self._waiters.remove(ticket)
                    self._condition.notify_all()
                    raise
                self._waiters.popleft()
            if cancel_event and cancel_event.is_set():
                raise InferenceCancelledError("Request cancelled")
            self._active = True
            self._entered_at = time.monotonic()
        return (time.monotonic() - started) * 1000

    def release(self) -> None:
        with self._condition:
            self._active = False
            self._entered_at = None
            self._condition.notify_all()

    def __enter__(self) -> "InferenceQueue":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()


class QueueLease:
    def __init__(
        self,
        queue: InferenceQueue,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.queue = queue
        self.cancel_event = cancel_event
        self.wait_ms = 0.0

    def __enter__(self) -> "QueueLease":
        self.wait_ms = self.queue.acquire(self.cancel_event)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.queue.release()
