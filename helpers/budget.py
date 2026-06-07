"""Per-chat budget guard for scribe model calls.

A runaway guard (per process), not a normal rate limit. Keeps the local scribe
from looping unbounded on a single chat.
"""
from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_calls: "defaultdict[str, int]" = defaultdict(int)


def allow_call(chat_id: str, max_calls: int) -> bool:
    """Return True and count a call if under budget; False once exhausted."""
    if max_calls is None or max_calls <= 0:
        return True
    with _lock:
        if _calls[chat_id] >= max_calls:
            return False
        _calls[chat_id] += 1
        return True


def reset(chat_id: str | None = None) -> None:
    with _lock:
        if chat_id is None:
            _calls.clear()
        else:
            _calls.pop(chat_id, None)
