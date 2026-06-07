"""Continuous background worker for the scribe super-ego.

A single daemon thread drains the observation queue, batches observations over a
debounce window, asks the local "scribe" model to summarize them, and writes the
result into a0_pen_paper. It is fully decoupled from Agent Zero's message loop,
so it runs continuously for the lifetime of the process while the plugin is
enabled. It never raises into the agent.

This is the "forget" half of the async fire-and-forget design: the observer
hook only enqueues; everything below happens off the agent's critical path.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable

from usr.plugins.a0_scribe.helpers import (
    budget,
    observation_bus,
    pen_paper_writer,
    scribe_client,
)

log = logging.getLogger("a0_scribe.worker")

_thread: threading.Thread | None = None
_lock = threading.Lock()
_stop = threading.Event()

_SYSTEM = (
    "You are the Scribe — a background documentarian for an AI agent. You receive "
    "a short log of the agent's most recent tool calls and their results. Write ONE "
    "concise note (2-5 sentences) capturing what the agent did, found, or decided — "
    "the kind of note that lets someone resume the work later. Begin your reply with "
    "exactly one section tag in square brackets, chosen from: [findings] [results] "
    "[insights] [notes] [decisions] [backtrack] [execution_log]. Then write the note. "
    "Only summarize what is in the log; never invent facts."
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

    bcfg = cfg.get("budget") or {}
    scfg = cfg.get("session") or {}
    max_calls = int(bcfg.get("max_calls_per_chat", 500))
    max_tokens = int(bcfg.get("max_tokens_per_call", 512))
    temperature = float(bcfg.get("temperature", 0.3))
    prefix = scfg.get("name_prefix", "scribe")
    default_section = scfg.get("default_section", "execution_log")
    prefer_focus = bool(scfg.get("prefer_chat_focus", True))

    for chat_id, observations in by_chat.items():
        if not budget.allow_call(chat_id, max_calls):
            continue
        messages = _build_prompt(observations)
        reply = scribe_client.complete(
            messages, max_tokens=max_tokens, temperature=temperature
        )
        if not reply:
            continue
        section, content = _parse_reply(reply, default_section)
        if not content:
            continue
        try:
            pen_paper_writer.write(
                chat_id, section, content, prefix=prefix, prefer_focus=prefer_focus
            )
        except Exception as exc:
            log.warning("scribe pen&paper write failed: %s", exc)


def _build_prompt(observations: list[dict[str, Any]]) -> list[dict[str, str]]:
    lines = []
    for obs in observations:
        tool = obs.get("tool_name", "?")
        args = obs.get("args_digest", "")
        result = obs.get("result_digest", "")
        lines.append(f"- tool={tool} | args={args} | result={result}")
    log_text = "\n".join(lines)[:6000]
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Agent activity log:\n{log_text}"},
    ]


def _parse_reply(reply: str, default_section: str) -> tuple[str, str]:
    try:
        from usr.plugins.a0_pen_paper.helpers.sessions_store import VALID_SECTIONS
    except Exception:
        VALID_SECTIONS = [
            "findings", "results", "insights", "notes",
            "decisions", "backtrack", "execution_log",
        ]
    text = (reply or "").strip()
    section = default_section
    if text.startswith("["):
        end = text.find("]")
        if end > 0:
            tag = text[1:end].strip().lower()
            if tag in VALID_SECTIONS:
                section = tag
                text = text[end + 1:].strip()
    return section, text
