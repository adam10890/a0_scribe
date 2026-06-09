"""Inject staged scribe nudges into the ego's prompt (Phase D).

Runs in message_loop_prompts_after. When authority_level is 'nudge' or 'enforce',
it drains the chat's pending advisory reminders and adds them to the prompt via
loop_data.extras_temporary (re-injected each turn, survives history compaction).
Advisory only — the ego is free to ignore them. Never blocks or breaks the loop.

Placement: extensions/python/message_loop_prompts_after/_61_scribe_nudge.py
"""
from __future__ import annotations

import logging

try:
    from helpers.extension import Extension
except ImportError:  # pragma: no cover
    from python.helpers.extension import Extension  # type: ignore

log = logging.getLogger("a0_scribe.nudge")


class ScribeNudge(Extension):
    async def execute(self, loop_data=None, **kwargs):
        try:
            from usr.plugins.a0_scribe.helpers import feedback_bus
            from usr.plugins.a0_scribe.helpers.config import load_config

            cfg = load_config(agent=getattr(self, "agent", None))
            if not cfg.get("enabled", True):
                return
            if loop_data is None or not hasattr(loop_data, "extras_temporary"):
                return

            agent = getattr(self, "agent", None)
            chat_id = ""
            if agent is not None and getattr(agent, "context", None) is not None:
                chat_id = getattr(agent.context, "id", "") or ""
            if not chat_id:
                return

            state_cfg = cfg.get("state") or {}
            if bool(state_cfg.get("inject_working_state", True)):
                try:
                    from usr.plugins.a0_scribe.helpers import state_prompt

                    prompt = state_prompt.load_for_chat(chat_id)
                    max_chars = int(state_cfg.get("prompt_max_chars", 2500))
                    if prompt:
                        loop_data.extras_temporary["scribe_working_state"] = prompt[:max_chars]
                except Exception:
                    pass

            if cfg.get("authority_level", "observe") not in ("nudge", "enforce"):
                return

            limit = int((cfg.get("feedback") or {}).get("inject_max_per_turn", 3))
            nudges = feedback_bus.drain_nudges(chat_id, limit)
            if not nudges:
                return

            body = "\n".join(f"- {n}" for n in nudges)
            loop_data.extras_temporary["scribe_nudges"] = (
                "## Scribe reminders (advisory)\n"
                "Your background scribe noticed the following. Act on them only if useful:\n"
                f"{body}"
            )
        except Exception as exc:  # never break the prompt pipeline
            log.debug("a0_scribe nudge skipped: %s", exc)
