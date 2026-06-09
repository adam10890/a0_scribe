"""Compact ego prompt rendering for Pen & Paper working state."""
from __future__ import annotations

from typing import Any

import yaml


def render_working_state(
    session_state: dict[str, Any],
    workflow_states: dict[str, dict[str, Any]],
    *,
    max_chars: int = 2500,
) -> str:
    """Render a compact, human-readable state block for the ego."""
    compact = {
        "session": (session_state or {}).get("session") or {},
        "working_set": (session_state or {}).get("working_set") or {},
        "active_workflows": (session_state or {}).get("active_workflows") or [],
        "workflow_states": workflow_states or {},
    }
    body = yaml.safe_dump(compact, sort_keys=False, allow_unicode=True)
    text = (
        "## Pen & Paper working state\n"
        "Use this compact state as the current operational truth when it is relevant. "
        "Do not treat it as a full transcript.\n"
        f"{body}"
    )
    return text[:max_chars]


def load_for_chat(chat_id: str, *, prefix: str = "scribe", prefer_focus: bool = True) -> str:
    """Resolve the chat workspace and render its current compact state."""
    from usr.plugins.a0_pen_paper.helpers import sessions_store
    from usr.plugins.a0_scribe.helpers import pen_paper_writer

    workspace = pen_paper_writer.resolve_session(chat_id, prefix=prefix, prefer_focus=prefer_focus)
    state = sessions_store.read_session_state(workspace)
    workflows: dict[str, dict[str, Any]] = {}
    for item in state.get("active_workflows") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        workflow_id = str(item["id"])
        workflows[workflow_id] = sessions_store.read_workflow_state(workspace, workflow_id)
    return render_working_state(state, workflows)
