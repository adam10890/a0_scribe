"""Soft workflow enforcement before a tool runs (Phase E).

Runs in tool_execute_before. When authority_level is 'enforce', it drains any
workflow-deviation notes the background scribe staged (judged off the ego's
critical path) and injects them as a history warning via agent.hist_add_warning.
SOFT enforcement: it advises/corrects, it does NOT block the tool. The ego and
user always retain control. Never blocks or breaks the tool pipeline.

Placement: extensions/python/tool_execute_before/_55_scribe_enforce.py
"""
from __future__ import annotations

import logging

try:
    from helpers.extension import Extension
except ImportError:  # pragma: no cover
    from python.helpers.extension import Extension  # type: ignore

log = logging.getLogger("a0_scribe.enforce")


class ScribeEnforce(Extension):
    async def execute(self, tool_name: str = "", tool_args=None, **kwargs):
        try:
            from usr.plugins.a0_scribe.helpers import feedback_bus
            from usr.plugins.a0_scribe.helpers.config import load_config

            cfg = load_config(agent=getattr(self, "agent", None))
            if not cfg.get("enabled", True):
                return
            if cfg.get("authority_level", "observe") != "enforce":
                return
            if not tool_name or tool_name.startswith("scribe"):
                return

            agent = getattr(self, "agent", None)
            if agent is None or not hasattr(agent, "hist_add_warning"):
                return
            chat_id = ""
            if getattr(agent, "context", None) is not None:
                chat_id = getattr(agent.context, "id", "") or ""
            if not chat_id:
                return

            limit = int((cfg.get("feedback") or {}).get("inject_max_per_turn", 3))
            notes = feedback_bus.drain_enforcements(chat_id, limit)
            if not notes:
                return

            body = "\n".join(f"- {n}" for n in notes)
            agent.hist_add_warning(
                "Scribe workflow check (advisory — you may proceed, but consider):\n" + body
            )
        except Exception as exc:  # never break the tool pipeline
            log.debug("a0_scribe enforce skipped: %s", exc)
