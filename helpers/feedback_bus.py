"""Per-chat staging of scribe feedback for the ego (Phases D & E).

The background worker (off the ego's critical path) decides whether to nudge or
flag a workflow deviation, and stages the message here. Ego-side extensions then
drain and inject it on the next turn:
  - nudges       -> message_loop_prompts_after (advisory, into the prompt)
  - enforcements -> tool_execute_before (a corrective warning before a tool runs)

Thread-safe; bounded per chat so feedback never accumulates unbounded.
"""
from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_nudges: "defaultdict[str, list[str]]" = defaultdict(list)
_enforcements: "defaultdict[str, list[str]]" = defaultdict(list)


def _stage(store: "defaultdict[str, list[str]]", chat_id: str, text: str, cap: int) -> None:
    text = (text or "").strip()
    if not chat_id or not text:
        return
    with _lock:
        q = store[chat_id]
        if text in q:  # de-dup repeats
            return
        q.append(text)
        if cap > 0 and len(q) > cap:
            del q[: len(q) - cap]


def _drain(store: "defaultdict[str, list[str]]", chat_id: str, limit: int) -> list[str]:
    if not chat_id:
        return []
    with _lock:
        q = store.get(chat_id) or []
        if not q:
            return []
        out = q[:limit] if limit and limit > 0 else list(q)
        store[chat_id] = q[len(out):]
        return out


def stage_nudge(chat_id: str, text: str, cap: int = 5) -> None:
    _stage(_nudges, chat_id, text, cap)


def drain_nudges(chat_id: str, limit: int = 3) -> list[str]:
    return _drain(_nudges, chat_id, limit)


def stage_enforcement(chat_id: str, text: str, cap: int = 5) -> None:
    _stage(_enforcements, chat_id, text, cap)


def drain_enforcements(chat_id: str, limit: int = 3) -> list[str]:
    return _drain(_enforcements, chat_id, limit)


def reset(chat_id: str | None = None) -> None:
    with _lock:
        if chat_id is None:
            _nudges.clear()
            _enforcements.clear()
        else:
            _nudges.pop(chat_id, None)
            _enforcements.pop(chat_id, None)
