"""Adapter: write scribe output into a0_pen_paper sessions.

a0_pen_paper's ``sessions_store`` is the single source of truth. Every entry the
scribe writes is tagged ``author="scribe"`` / ``source="scribe"`` so Adam can
audit exactly what the super-ego did (transparency guardrail). All imports are
lazy so this module loads even when a0_pen_paper is absent.
"""
from __future__ import annotations

from typing import Any


def _store():
    from usr.plugins.a0_pen_paper.helpers import sessions_store

    return sessions_store


def resolve_session(
    chat_id: str, *, prefix: str = "scribe", prefer_focus: bool = True
) -> str:
    """Pick the workspace to write into: the chat's focused session if one
    exists, otherwise a per-chat scribe session (created on demand)."""
    store = _store()
    name = None
    safe = "".join(c for c in (chat_id or "session") if c.isalnum() or c in "_-")
    fallback_name = f"{prefix}_{safe or 'session'}"
    if prefer_focus and chat_id:
        try:
            focus = store.read_focus(chat_id)
            if isinstance(focus, dict):
                name = focus.get("workspace")
        except Exception:
            name = None
    if not name and prefer_focus and chat_id:
        try:
            sessions = store.list_sessions(chat_id=chat_id, chat_only=True).get("sessions") or []
            current = [
                item.get("name")
                for item in sessions
                if isinstance(item, dict) and item.get("is_current_chat") and item.get("name")
            ]
            human_named = [
                item for item in current if str(item) != fallback_name
            ]
            if human_named:
                name = str(human_named[0])
            elif current:
                name = str(current[0])
        except Exception:
            name = None
    if not name:
        name = fallback_name
    try:
        store.ensure_session(name, chat_id)
    except Exception:
        pass
    return name


def write(
    chat_id: str,
    section: str,
    content: str,
    *,
    prefix: str = "scribe",
    prefer_focus: bool = True,
) -> dict[str, Any]:
    """Append a scribe note to the resolved session. Retries once on stale etag."""
    store = _store()
    name = resolve_session(chat_id, prefix=prefix, prefer_focus=prefer_focus)

    try:
        etag = store.get_session(name).get("etag", "")
    except Exception:
        etag = ""

    res = store.append_section(
        name, section, content, etag, author="scribe", source="scribe"
    )
    if isinstance(res, dict) and not res.get("ok") and res.get("error") == "stale":
        try:
            fresh = store.get_session(name).get("etag", "")
            res = store.append_section(
                name, section, content, fresh, author="scribe", source="scribe"
            )
        except Exception:
            pass

    try:
        store.write_focus(workspace=name, section=section, action="scribe", chat_id=chat_id)
    except Exception:
        pass

    return res if isinstance(res, dict) else {"ok": False}
