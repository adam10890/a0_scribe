"""Structured state events for the scribe State-DOX layer.

The scribe observes compact runtime events, tags them, and uses those tags to
activate per-session Pen & Paper workflow state files. This module is deliberately
pure so it can be tested without Agent Zero or router services.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re

# Built-in workflow definitions. These remain the authoritative fallback when
# Pen & Paper (the State-DOX template owner) is unavailable or older than the
# publish contract. Live maps are produced by _load_workflow_maps(), which merges
# these defaults with sessions_store.list_state_dox_templates().
_DEFAULT_WORKFLOW_TAGS: dict[str, set[str]] = {
    "planning": {"planning", "design", "architecture", "decision_candidate"},
    "implementation": {"implementation", "file_change", "code_change"},
    "debugging": {"tool_error", "error_log", "test_failure", "unexpected_behavior"},
    "verification": {"verification", "test_result", "compile_result"},
    "research": {"research", "search", "file_read", "finding"},
}

_DEFAULT_WORKFLOW_SKILLS: dict[str, str] = {
    "planning": "scribe-workflow-planning",
    "implementation": "scribe-workflow-implementation",
    "debugging": "scribe-workflow-debugging",
    "verification": "scribe-workflow-verification",
    "research": "scribe-workflow-research",
}

_DEFAULT_TAGS = set().union(*_DEFAULT_WORKFLOW_TAGS.values())
_TAG_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{1,80}$")
_TAG_MARKER_RE = re.compile(
    r"\b(?:SCRIBE_TAGS?|STATE_DOX_TAGS?)\s*[:=]\s*([a-z0-9_.:,\-\s]{1,300})",
    flags=re.IGNORECASE,
)

_CACHE_TTL = 30.0
_CACHE_TTL_ON_ERROR = 5.0
_cache_lock = threading.Lock()
_cache: dict[str, Any] | None = None
_cache_expiry: float = 0.0


def _pp_state_dox_templates() -> list[dict[str, Any]]:
    """Read State-DOX templates from Pen & Paper (the storage owner). Isolated so
    tests can stub it and so the import stays lazy. Raises if a0_pen_paper is
    missing or too old to expose list_state_dox_templates(); callers fall back."""
    from usr.plugins.a0_pen_paper.helpers import sessions_store

    return sessions_store.list_state_dox_templates()


def _build_workflow_maps(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tags: dict[str, set[str]] = {k: set(v) for k, v in _DEFAULT_WORKFLOW_TAGS.items()}
    skills: dict[str, str | None] = dict(_DEFAULT_WORKFLOW_SKILLS)
    ids: list[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        wf_id = str(row.get("id") or "").strip()
        if not wf_id:
            continue
        row_tags = row.get("activation_tags")
        if isinstance(row_tags, list):
            tags[wf_id] = {str(t) for t in row_tags}
        elif wf_id not in tags:
            tags[wf_id] = set()
        skill = row.get("skill")
        skills[wf_id] = str(skill) if skill else skills.get(wf_id)
        if wf_id not in ids:
            ids.append(wf_id)
    # Built-ins must always be activatable, even on partial or empty PP data.
    for wf_id in _DEFAULT_WORKFLOW_TAGS:
        if wf_id not in ids:
            ids.append(wf_id)
    return {"tags": tags, "skills": skills, "ids": ids}


def _load_workflow_maps() -> dict[str, Any]:
    """Return {"tags","skills","ids"} merging built-ins with PP State-DOX templates.
    Cached (TTL). NEVER raises — falls back to built-ins on any error."""
    global _cache, _cache_expiry
    now = time.monotonic()
    with _cache_lock:
        if _cache is not None and now < _cache_expiry:
            return _cache
    try:
        rows = _pp_state_dox_templates()
        maps = _build_workflow_maps(rows if isinstance(rows, list) else [])
        ttl = _CACHE_TTL
    except Exception:
        maps = _build_workflow_maps([])
        ttl = _CACHE_TTL_ON_ERROR
    with _cache_lock:
        _cache = maps
        _cache_expiry = time.monotonic() + ttl
    return maps


def invalidate_workflow_cache() -> None:
    """Drop cached workflow maps (forces reload on next access)."""
    global _cache, _cache_expiry
    with _cache_lock:
        _cache = None
        _cache_expiry = 0.0


def workflow_tags() -> dict[str, set[str]]:
    return _load_workflow_maps()["tags"]


def workflow_skills() -> dict[str, str | None]:
    return _load_workflow_maps()["skills"]


def workflow_ids() -> list[str]:
    return list(_load_workflow_maps()["ids"])


def _skills_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "skills"


def _skill_exists(skill: str | None) -> bool:
    try:
        return bool(skill) and (_skills_dir() / str(skill) / "SKILL.md").exists()
    except Exception:
        return False


def _resolve_skill(workflow_id: str, declared: str | None) -> str:
    """declared (if its SKILL.md exists) -> scribe-workflow-<id> (if exists) -> scribe-core."""
    return _skill_resolution(workflow_id, declared)["skill"]


def _skill_resolution(workflow_id: str, declared: str | None) -> dict[str, str]:
    if _skill_exists(declared):
        return {"skill": str(declared)}
    candidate = f"scribe-workflow-{workflow_id}"
    if _skill_exists(candidate):
        result = {"skill": candidate}
        if declared:
            result["warning"] = (
                f"Declared Scribe skill '{declared}' was not found; "
                f"using conventional skill '{candidate}'."
            )
        return result
    result = {"skill": "scribe-core"}
    if declared:
        result["warning"] = (
            f"Declared Scribe skill '{declared}' was not found; using scribe-core."
        )
    else:
        result["warning"] = (
            f"No workflow skill found for '{workflow_id}'; using scribe-core."
        )
    return result


def _runtime_activation_tags() -> set[str]:
    """Custom activation tags published by Pen & Paper State-DOX templates."""
    tags: set[str] = set()
    for values in workflow_tags().values():
        for tag in values:
            text = str(tag).strip().lower()
            if text and text not in _DEFAULT_TAGS and _TAG_TOKEN_RE.match(text):
                tags.add(text)
    return tags


def _extract_marked_runtime_tags(text: str, known: set[str]) -> set[str]:
    found: set[str] = set()
    for match in _TAG_MARKER_RE.finditer(text or ""):
        for raw in re.split(r"[\s,;]+", match.group(1)):
            tag = raw.strip().lower()
            if tag in known:
                found.add(tag)
    return found


def _extract_runtime_tags(
    *,
    args_text: str,
    result_text: str,
    analysis_text: str,
    read_only_inspection: bool,
) -> set[str]:
    known = _runtime_activation_tags()
    if not known:
        return set()

    found = _extract_marked_runtime_tags(args_text, known)
    if not read_only_inspection:
        found.update(_extract_marked_runtime_tags(result_text, known))
        keyword_text = f"{args_text} {analysis_text}".lower()
        for tag in known:
            if re.search(rf"(?<![a-z0-9_.:-]){re.escape(tag)}(?![a-z0-9_.:-])", keyword_text):
                found.add(tag)
    return found


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


def _is_state_artifact_audit(haystack: str) -> bool:
    normalized = (haystack or "").replace("\\", "/").lower()
    return any(
        token in normalized
        for token in (
            "/state/events.jsonl",
            "/state/session_state.yaml",
            "/state/workflows/",
        )
    )


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
    raw_args = _stringify(obs.get("args_digest", ""))
    raw_result = _stringify(obs.get("result_digest", ""))
    haystack = f"{tool} {analysis}".lower()
    raw_haystack = f"{tool} {raw_args} {raw_result} {analysis}".lower()

    tags = {"tool_call"}
    read_only_inspection = _is_read_only_inspection(haystack)
    verification_activity = _is_verification_activity(haystack)
    state_artifact_audit = _is_state_artifact_audit(raw_haystack)

    if state_artifact_audit:
        tags.add("state_audit")
    else:
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
        tags.update(
            _extract_runtime_tags(
                args_text=raw_args,
                result_text=raw_result,
                analysis_text=analysis,
                read_only_inspection=read_only_inspection,
            )
        )

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
    if "state_audit" in tags:
        return _compact(f"{tool}: State-DOX audit inspection: {result or args}", 220)
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
    if "state_audit" in tags:
        return []
    wf_tags = workflow_tags()
    active: list[str] = []
    for workflow_id in available:
        if tags & wf_tags.get(workflow_id, set()):
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
    skills = workflow_skills()
    active_skills = []
    for workflow_id in active_workflows:
        item = {"workflow": workflow_id}
        item.update(_skill_resolution(workflow_id, skills.get(workflow_id)))
        active_skills.append(item)
    return {
        "trigger_event": trigger_event,
        "recent_events": recent_events[-20:],
        "session_state": session_state,
        "active_workflows": active_workflows,
        "active_skills": active_skills,
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
    skills = workflow_skills()
    item = {
        "id": workflow_id,
        "state": "active",
        "file": f"workflows/{workflow_id}.yaml",
        "reason": f"Activated by event tags: {', '.join(event.get('tags') or [])}",
    }
    item.update(_skill_resolution(workflow_id, skills.get(workflow_id)))
    return item


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
