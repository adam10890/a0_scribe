"""Continuous background worker for the scribe super-ego.

A single daemon thread drains the observation queue, batches observations over a
debounce window, asks the local "scribe" model to summarize them, and writes the
result into a0_pen_paper. It is fully decoupled from Agent Zero's message loop,
so it runs continuously for the lifetime of the process while the plugin is
enabled. It never raises into the agent.

This is the "forget" half of the async fire-and-forget design: the observer hook
only enqueues; everything below happens off the agent's critical path.

Authority levels (config `authority_level`):
  - observe : document only (write notes to Pen & Paper).
  - nudge   : also emit advisory reminders (Phase D) -> feedback_bus.stage_nudge.
  - enforce : also flag workflow deviations (Phase E) -> feedback_bus.stage_enforcement.
The ego-side extensions inject staged nudges/deviations on the next turn.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable

from usr.plugins.a0_scribe.helpers import (
    budget,
    feedback_bus,
    observation_bus,
    pen_paper_writer,
    scribe_client,
)

log = logging.getLogger("a0_scribe.worker")

_thread: threading.Thread | None = None
_lock = threading.Lock()
_stop = threading.Event()

_SYSTEM_BASE = (
    "You are the Scribe — a background documentarian for an AI agent. You receive "
    "a short log of the agent's most recent tool calls and their results. Write ONE "
    "concise note (2-5 sentences) capturing what the agent did, found, or decided — "
    "the kind of note that lets someone resume the work later. Begin your reply with "
    "exactly one section tag in square brackets, chosen from: [findings] [results] "
    "[insights] [notes] [decisions] [backtrack] [execution_log]. Then write the note. "
    "Only summarize what is in the log; never invent facts."
)

_SYSTEM_NUDGE = (
    "\n\nAFTER the note, only if the agent clearly skipped recording something "
    "important or is about to lose track, add one final line starting with 'NUDGE: ' "
    "and a single short reminder. If nothing is needed, do not add a NUDGE line."
)

_SYSTEM_ENFORCE = (
    "\n\nAlso, only if the agent's recent actions clearly deviate from a sane workflow "
    "(e.g., acting without recording findings, repeating a step that already failed, "
    "skipping verification before concluding), add one final line starting with "
    "'DEVIATION: ' and a single short corrective instruction. Omit it if not needed."
)


def ensure_running(config_provider: Callable[[], dict] | dict | None) -> None:
    """Idempotently start the worker thread. Safe to call on every hook."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop.clear()
        _thread = threading.Thread(
            target=_run, args=(config_provider,), name="a0_scribe_worker", daemon=True
        )
        _thread.start()
        log.info("a0_scribe worker thread started")


def stop() -> None:
    _stop.set()


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def _safe_cfg(config_provider: Callable[[], dict] | dict | None) -> dict:
    try:
        cfg = config_provider() if callable(config_provider) else config_provider
        return cfg or {}
    except Exception:
        return {}


def _run(config_provider) -> None:
    while not _stop.is_set():
        try:
            cfg = _safe_cfg(config_provider)
            if not cfg.get("enabled", True):
                time.sleep(2.0)
                continue
            batch = _drain_batch(cfg)
            if batch:
                _process(batch, cfg)
        except Exception as exc:  # the worker must never die
            log.warning("scribe worker cycle error: %s", exc)
            time.sleep(1.0)


def _drain_batch(cfg: dict) -> list[dict[str, Any]]:
    q = observation_bus.get_queue()
    observe = cfg.get("observe") or {}
    debounce = float(observe.get("debounce_seconds", 4))
    max_batch = int(observe.get("max_batch", 12))

    try:
        first = q.get(timeout=1.0)  # short block so _stop stays responsive
    except queue.Empty:
        return []

    batch = [first]
    deadline = time.monotonic() + debounce
    while len(batch) < max_batch:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            batch.append(q.get(timeout=remaining))
        except queue.Empty:
            break
    return batch


def _process(batch: list[dict[str, Any]], cfg: dict) -> None:
    by_chat: dict[str, list[dict[str, Any]]] = {}
    for obs in batch:
        by_chat.setdefault(obs.get("chat_id") or "", []).append(obs)

    authority = (cfg.get("authority_level") or "observe").lower()
    bcfg = cfg.get("budget") or {}
    scfg = cfg.get("session") or {}
    fcfg = cfg.get("feedback") or {}
    max_calls = int(bcfg.get("max_calls_per_chat", 500))
    max_tokens = int(bcfg.get("max_tokens_per_call", 512))
    temperature = float(bcfg.get("temperature", 0.3))
    prefix = scfg.get("name_prefix", "scribe")
    default_section = scfg.get("default_section", "execution_log")
    prefer_focus = bool(scfg.get("prefer_chat_focus", True))
    cap = int(fcfg.get("max_pending_per_chat", 5))

    for chat_id, observations in by_chat.items():
        if not budget.allow_call(chat_id, max_calls):
            continue
        messages = _build_prompt(observations, authority)
        reply = scribe_client.complete(
            messages, max_tokens=max_tokens, temperature=temperature
        )
        if not reply:
            continue
        section, content, nudge, deviation = _parse_reply(reply, default_section)

        if content:
            _write(chat_id, section, content, prefix, prefer_focus)

        # Phase D — advisory nudges
        if nudge and authority in ("nudge", "enforce"):
            feedback_bus.stage_nudge(chat_id, nudge, cap=cap)
            _write(chat_id, "notes", f"NUDGE (scribe): {nudge}", prefix, prefer_focus)

        # Phase E — soft workflow enforcement
        if deviation and authority == "enforce":
            feedback_bus.stage_enforcement(chat_id, deviation, cap=cap)
            _write(chat_id, "backtrack", f"DEVIATION (scribe): {deviation}", prefix, prefer_focus)


def _write(chat_id: str, section: str, content: str, prefix: str, prefer_focus: bool) -> None:
    try:
        pen_paper_writer.write(
            chat_id, section, content, prefix=prefix, prefer_focus=prefer_focus
        )
    except Exception as exc:
        log.warning("scribe pen&paper write failed: %s", exc)


def _build_prompt(observations: list[dict[str, Any]], authority: str) -> list[dict[str, str]]:
    system = _SYSTEM_BASE
    if authority in ("nudge", "enforce"):
        system += _SYSTEM_NUDGE
    if authority == "enforce":
        system += _SYSTEM_ENFORCE

    lines = []
    for obs in observations:
        tool = obs.get("tool_name", "?")
        args = obs.get("args_digest", "")
        result = obs.get("result_digest", "")
        lines.append(f"- tool={tool} | args={args} | result={result}")
    log_text = "\n".join(lines)[:6000]
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Agent activity log:\n{log_text}"},
    ]


def _parse_reply(reply: str, default_section: str) -> tuple[str, str, str | None, str | None]:
    try:
        from usr.plugins.a0_pen_paper.helpers.sessions_store import VALID_SECTIONS
    except Exception:
        VALID_SECTIONS = [
            "findings", "results", "insights", "notes",
            "decisions", "backtrack", "execution_log",
        ]

    text = (reply or "").strip()
    # Strip a leading/trailing code fence if the model wrapped its reply.
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()

    nudge: str | None = None
    deviation: str | None = None
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("nudge:"):
            cand = stripped[6:].strip()
            if cand:
                nudge = cand
        elif low.startswith("deviation:"):
            cand = stripped[10:].strip()
            if cand:
                deviation = cand
        else:
            kept.append(line)

    body = "\n".join(kept).strip()
    section = default_section
    if body.startswith("["):
        end = body.find("]")
        if end > 0:
            tag = body[1:end].strip().lower()
            if tag in VALID_SECTIONS:
                section = tag
                body = body[end + 1:].strip()
    return section, body, nudge, deviation
