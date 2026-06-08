"""Global tool observer for the scribe super-ego (tool_execute_after).

Fires after EVERY tool call the ego makes. Builds a compact observation and
enqueues it (non-blocking) for the background worker, then makes sure the worker
is running. This is the "fire" half of the async fire-and-forget design — it must
never block or break the agent's tool pipeline.

Placement: extensions/python/tool_execute_after/_60_scribe_observe.py
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

try:
    from helpers.extension import Extension
except ImportError:  # pragma: no cover
    from python.helpers.extension import Extension  # type: ignore

log = logging.getLogger("a0_scribe.observe")

_MAX_DIGEST = 1200
_SIGNAL_TERMS = (
    "py_compile",
    "unittest",
    "pytest",
    "traceback",
    "error",
    "failed",
    "failure",
    "no such file",
    "errno",
    "exit code",
    "syntaxerror",
    "assertionerror",
    " ok",
    "... ok",
)


def _signal_excerpt(text: str, term: str, radius: int = 120) -> str:
    low = text.lower()
    idx = low.find(term)
    if idx < 0:
        return ""
    start = max(0, idx - radius)
    end = min(len(text), idx + len(term) + radius)
    return text[start:end].strip()


def _digest(value, limit: int = _MAX_DIGEST) -> str:
    try:
        text = value if isinstance(value, str) else str(value)
    except Exception:
        return ""
    activity_matches = list(
        re.finditer(r"(?:={2,}\s*)?(?:START\s+)?ACTIVITY\b", text, flags=re.IGNORECASE)
    )
    if activity_matches:
        text = text[activity_matches[-1].start() :]
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact

    signal_lines = []
    for line in str(text).splitlines():
        normalized = " ".join(line.split())
        if not normalized:
            continue
        low = normalized.lower()
        for term in _SIGNAL_TERMS:
            if term in low:
                excerpt = _signal_excerpt(normalized, term)
                if excerpt:
                    signal_lines.append(excerpt)
                break

    parts = [compact[: max(120, limit // 4)]]
    if signal_lines:
        parts.append("SIGNALS: " + " | ".join(signal_lines[:8]))
    parts.append(compact[-max(120, limit // 4):])
    return " ".join(parts)[:limit]


def _response_kvps(response) -> dict:
    kvps = getattr(response, "kvps", None)
    if isinstance(kvps, dict):
        return kvps
    additional = getattr(response, "additional", None)
    if isinstance(additional, dict):
        return additional
    if isinstance(response, dict):
        raw = response.get("kvps")
        if isinstance(raw, dict):
            return raw
        raw = response.get("additional")
        if isinstance(raw, dict):
            return raw
    return {}


def _current_tool_args(agent) -> dict:
    tool = getattr(getattr(agent, "loop_data", None), "current_tool", None)
    args = getattr(tool, "args", None)
    return args if isinstance(args, dict) else {}


def _args_digest(tool_args, response=None, agent=None) -> str:
    parts = []
    effective_args = tool_args if tool_args is not None else _current_tool_args(agent)
    if effective_args:
        parts.append(_digest(effective_args))
    kvps = _response_kvps(response)
    for key in ("command", "runtime", "path", "action", "name"):
        value = (
            effective_args.get(key)
            if isinstance(effective_args, dict) and effective_args.get(key)
            else kvps.get(key)
        )
        if value:
            parts.append(f"{key}={_digest(value, 500)}")
    return " ".join(part for part in parts if part)


class ScribeObserve(Extension):
    async def execute(self, tool_name: str = "", tool_args=None, response=None, **kwargs):
        try:
            from usr.plugins.a0_scribe.helpers import observation_bus, scribe_worker
            from usr.plugins.a0_scribe.helpers.config import load_config

            cfg = load_config(agent=getattr(self, "agent", None))
            if not cfg.get("enabled", True):
                return

            ignore = set((cfg.get("observe") or {}).get("ignore_tools") or [])
            if not tool_name or tool_name in ignore or tool_name.startswith("scribe"):
                return

            chat_id = ""
            agent = getattr(self, "agent", None)
            if agent is not None and getattr(agent, "context", None) is not None:
                chat_id = getattr(agent.context, "id", "") or ""

            result = getattr(response, "message", response)

            observation_bus.enqueue(
                {
                    "chat_id": chat_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "tool_name": tool_name,
                    "args_digest": _args_digest(tool_args, response, agent),
                    "result_digest": _digest(result),
                }
            )

            # Lazy-start so observation works even if agent_init didn't run.
            scribe_worker.ensure_running(
                lambda: load_config(agent=getattr(self, "agent", None))
            )
        except Exception as exc:  # never break the tool pipeline
            log.debug("a0_scribe observe skipped: %s", exc)
