"""Global tool observer for the scribe super-ego (tool_execute_after).

Fires after EVERY tool call the ego makes. Builds a compact observation and
enqueues it (non-blocking) for the background worker, then makes sure the worker
is running. This is the "fire" half of the async fire-and-forget design — it must
never block or break the agent's tool pipeline.

Placement: extensions/python/tool_execute_after/_60_scribe_observe.py
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

try:
    from helpers.extension import Extension
except ImportError:  # pragma: no cover
    from python.helpers.extension import Extension  # type: ignore

log = logging.getLogger("a0_scribe.observe")

_MAX_DIGEST = 700


def _digest(value, limit: int = _MAX_DIGEST) -> str:
    try:
        text = value if isinstance(value, str) else str(value)
    except Exception:
        return ""
    return " ".join(text.split())[:limit]


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
                    "args_digest": _digest(tool_args),
                    "result_digest": _digest(result),
                }
            )

            # Lazy-start so observation works even if agent_init didn't run.
            scribe_worker.ensure_running(
                lambda: load_config(agent=getattr(self, "agent", None))
            )
        except Exception as exc:  # never break the tool pipeline
            log.debug("a0_scribe observe skipped: %s", exc)
