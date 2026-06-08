"""Structured state events for the scribe State-DOX layer.

The scribe observes compact runtime events, tags them, and uses those tags to
activate per-session Pen & Paper workflow state files. This module is deliberately
pure so it can be tested without Agent Zero or router services.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re

WORKFLOW_TAGS: dict[str, set[str]] = {
    "planning": {"planning", "design", "architecture", "decision_candidate"},
    "implementation": {"implementation", "file_change", "code_change"},
    "debugging": {"tool_error", "error_log", "test_failure", "unexpected_behavior"},
    "verification": {"verification", "test_result", "compile_result"},
    "research": {"research", "search", "file_read", "finding"},
}

WORKFLOW_SKILLS: dict[str, str] = {
    "planning": "scribe-workflow-planning",
    "implementation": "scribe-workflow-implementation",
    "debugging": "scribe-workflow-debugging",
    "verification": "scribe-workflow-verification",
    "research": "scribe-workflow-research",
}


def _compact(value: Any, limit: int = 700) -> str:
    try:
        text = value if isinstance(value, str) else str(value)
    except Exception:
        return ""
    return " ".join(text.split())[:limit]


def _stringify(value: Any) -> str:
    try:
        return value if isinstance(value, str) else str(value)
    except Exception:
        return ""


def _analysis_text(args: Any, result: Any) -> str:
    """Return the newest meaningful activity slice from a terminal-like digest."""
    text = f"{_stringify(args)} {_stringify(result)}".strip()
    if not text:
        return ""

    activity_matches = list(
        re.finditer(r"(?:={2,}\s*)?(?:START\s+)?ACTIVITY\b", text, flags=re.IGNORECASE)
    )
    if activity_matches:
        text = text[activity_matches[-1].start() :]
        before_signals, sep, _after_signals = text.partition("SIGNALS:")
        if sep and before_signals.strip():
            text = before_signals
    else:
        before_signals, sep, after_signals = text.partition("SIGNALS:")
        if sep:
            low_before = before_signals.lower()
            if any(token in low_before for token in ("tool failed", "error", "failed", "errno")):
                text = before_signals
            elif _contains_read_only_command(low_before):
                text = before_signals
            elif after_signals.strip():
                text = after_signals

    for noisy_field in ("current_focus:", "session_state.yaml:", "events.jsonl:"):
        before_noisy, sep, _after_noisy = text.partition(noisy_field)
        if sep and before_noisy.strip():
            text = before_noisy

    return _compact(text, 1000)


def _contains_read_only_command(haystack: str) -> bool:
    return bool(re.search(r"(?:^|\s)(?:[a-z]:)?[/\\][^:]+:\s+\S+", haystack)) or any(
        token in haystack
        for token in (
            "cat ",
            "ls ",
            "dir ",
            "find ",
            "get-content",
            "type ",
            "rg ",
            "ripgrep",
            "read_text",
            "sed ",
            "skill.md",
        )
    )


def _is_read_only_inspection(haystack: str) -> bool:
    return _contains_read_only_command(haystack)


def _looks_like_file_listing(haystack: str) -> bool:
    paths = re.findall(r"(?:^|\s)(?:[a-z]:)?[/\\][^\s:]+", haystack)
    return len(set(path.strip() for path in paths)) >= 2


def _is_verification_activity(haystack: str) -> bool:
    return bool(
        re.search(r"\bpython\s+-m\s+py_compile\b", haystack)
        or re.search(r"\bpy_compile\b", haystack)
        or re.search(r"\b(pytest|unittest)\b", haystack)
        or re.search(r"\b(test|tests)\s+(passed|failed|ok)\b", haystack)
    )


def normalize_observation(obs: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw observer payload into a compact tagged event."""
    tool = str(obs.get("tool_name") or "")
    args = _compact(obs.get("args_digest", ""))
    result = _compact(obs.get("result_digest", ""))
    analysis = _analysis_text(obs.get("args_digest", ""), obs.get("result_digest", ""))
    haystack = f"{tool} {analysis}".lower()

    tags = {"tool_call"}
    read_only_inspection = _is_read_only_inspection(haystack)
    verification_activity = _is_verification_activity(haystack)
    if (not read_only_inspection or verification_activity) and any(
        token in haystack
        for token in (
            "traceback",
            "exception",
            "exit code: 1",
            "errno",
            "no such file",
            "not found",
            "syntaxerror",
        )
    ):
        tags.update({"tool_error", "unexpected_behavior"})
    elif not read_only_inspection and re.search(r"\berror\b", haystack):
        tags.update({"tool_error", "unexpected_behavior"})
    if verification_activity and any(
        token in haystack for token in ("fail", "failed", "assertionerror")
    ):
        tags.update({"test_failure", "unexpected_behavior"})
    if verification_activity:
        tags.update({"verification", "test_result"})
    if verification_activity and ("py_compile" in haystack or "compile" in haystack):
        tags.add("compile_result")
    if tool in {"apply_patch"} or any(token in haystack for token in ("git diff", "modified", "file changed")):
        tags.update({"implementation", "file_change", "code_change"})
    if (
        read_only_inspection
        or ("tool_error" not in tags and _looks_like_file_listing(haystack))
        or any(token in haystack for token in ("search", "finding"))
    ):
        tags.update({"research", "search", "file_read"})
    if not read_only_inspection and any(
        token in haystack for token in ("plan", "design", "architecture", "decision")
    ):
        tags.update({"planning", "decision_candidate"})

    summary = _semantic_summary(tool, args, analysis or result, tags)
    return {
        "ts": obs.get("ts") or datetime.now(timezone.utc).isoformat(),
        "chat_id": obs.get("chat_id") or "",
        "type": "tool_result",
        "source": "scribe_observer",
        "tool_name": tool,
        "tags": sorted(tags),
        "summary": _compact(summary, 500),
        "args_digest": args,
        "result_digest": result,
    }


def _semantic_summary(tool: str, args: str, result: str, tags: set[str]) -> str:
    text = f"{args} {result}".strip()
    py_compile = re.search(r"python\s+-m\s+py_compile\s+([^\s]+)", text)
    if py_compile:
        target = py_compile.group(1)
        status = "failed" if {"tool_error", "test_failure"} & tags else "passed"
        detail = ""
        detail_match = re.search(
            r"(\[Errno\s+\d+\][^|]{0,120}|No such file[^|]{0,120}|SyntaxError[^|]{0,120})",
            text,
            flags=re.IGNORECASE,
        )
        if detail_match:
            detail = f": {detail_match.group(1).strip()}"
        return _compact(f"{tool}: py_compile {status} for {target}{detail}", 220)

    if "verification" in tags:
        status = "failed" if {"tool_error", "test_failure"} & tags else "passed"
        return _compact(f"{tool}: verification {status}: {result or args}", 220)
    if "research" in tags:
        return _compact(f"{tool}: source inspection: {result or args}", 220)
    if {"tool_error", "test_failure"} & tags:
        return _compact(f"{tool}: tool failed: {result or args}", 220)
    return _compact(f"{tool}: {result or args}".strip(": "), 220)


def _next_action_for_event(event: dict[str, Any]) -> str:
    tags = set(event.get("tags") or [])
    summary = str(event.get("summary") or "")
    if {"tool_error", "test_failure"} & tags and "verification" in tags:
        return _compact(f"Fix the verification failure captured in: {summary}", 180)
    if {"tool_error", "test_failure"} & tags:
        return _compact(f"Investigate and fix the observed tool failure: {summary}", 180)
    if "verification" in tags:
        return "Record the passed verification and continue the active workflow."
    if "research" in tags:
        return "Extract the relevant finding from the inspected source."
    return ""


def select_workflows(event: dict[str, Any], available: list[str] | tuple[str, ...]) -> list[str]:
    """Return workflow IDs activated by an event, preserving available order."""
    tags = set(event.get("tags") or [])
    active: list[str] = []
    for workflow_id in available:
        if tags & WORKFLOW_TAGS.get(workflow_id, set()):
            active.append(workflow_id)
    return active


def build_state_envelope(
    *,
    trigger_event: dict[str, Any],
    recent_events: list[dict[str, Any]],
    session_state: dict[str, Any],
    workflow_states: dict[str, dict[str, Any]],
    active_workflows: list[str],
) -> dict[str, Any]:
    """Build the compact prompt payload for one scribe state update."""
    return {
        "trigger_event": trigger_event,
        "recent_events": recent_events[-20:],
        "session_state": session_state,
        "active_workflows": active_workflows,
        "active_skills": [
            {"workflow": workflow_id, "skill": WORKFLOW_SKILLS[workflow_id]}
            for workflow_id in active_workflows
            if workflow_id in WORKFLOW_SKILLS
        ],
        "workflow_states": {
            key: value for key, value in workflow_states.items() if key in active_workflows
        },
    }


def session_patch_for_event(
    event: dict[str, Any],
    active_workflows: list[str],
    *,
    existing_active_workflows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Deterministic baseline state patch applied before model refinement."""
    return _session_patch_for_event(
        event,
        active_workflows,
        existing_active_workflows=existing_active_workflows,
    )


def _workflow_item(workflow_id: str, event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": workflow_id,
        "state": "active",
        "file": f"workflows/{workflow_id}.yaml",
        "skill": WORKFLOW_SKILLS.get(workflow_id),
        "reason": f"Activated by event tags: {', '.join(event.get('tags') or [])}",
    }


def _session_patch_for_event(
    event: dict[str, Any],
    active_workflows: list[str],
    *,
    existing_active_workflows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    modes = [tag for tag in event.get("tags", []) if tag in {"planning", "research", "verification"}]
    merged_workflows = [_workflow_item(workflow_id, event) for workflow_id in active_workflows]
    working_set = {
        "current_focus": event.get("summary", ""),
    }
    next_action = _next_action_for_event(event)
    if next_action:
        working_set["next_action"] = next_action

    return {
        "working_set": {
            **working_set,
        },
        "active_workflows": merged_workflows,
        "tags": {
            "modes": modes,
        },
    }


def workflow_patch_for_event(event: dict[str, Any]) -> dict[str, Any]:
    """Small patch shared by activated workflow live copies."""
    return {
        "state": {
            "phase": "active",
            "last_evidence_event": event.get("id"),
        }
    }
