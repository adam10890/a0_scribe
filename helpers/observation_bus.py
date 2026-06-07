"""Thread-safe observation queue shared by the scribe observer and worker.

The observer (an async tool hook on the agent's loop) enqueues; the worker (a
daemon thread) drains. A bounded queue with oldest-drop backpressure keeps the
agent's path non-blocking — the scribe summarizes, it does not need every event.
"""
from __future__ import annotations

import queue
from typing import Any

_MAXSIZE = 1000
_QUEUE: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=_MAXSIZE)


def enqueue(obs: dict[str, Any]) -> None:
    """Non-blocking put. Drops the oldest item if the queue is full."""
    try:
        _QUEUE.put_nowait(obs)
    except queue.Full:
        try:
            _QUEUE.get_nowait()
        except queue.Empty:
            pass
        try:
            _QUEUE.put_nowait(obs)
        except queue.Full:
            pass


def get_queue() -> "queue.Queue[dict[str, Any]]":
    return _QUEUE
