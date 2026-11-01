"""Fail-closed HTTP client for one pinned, local Imperium harness.

No host discovery, retries, redirects, proxy inheritance, or content logging.
Counters and the circuit breaker are process-local; deterministic recording is
owned by the worker and continues when inference is skipped.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import config

_lock = threading.Lock()
_counts = dict.fromkeys(
    ("ok", "busy", "unavailable", "timeout", "auth", "invalid_response", "error", "circuit_open_skips"),
    0,
)
_failures = 0
_open_until = 0.0
_probe_inflight = False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect rejected", headers, fp)


def health() -> dict[str, int]:
    """Return counters only: no endpoint, credentials, prompts, or responses."""
    with _lock:
        return dict(_counts)


def reset() -> None:
    """Reset process-local counters and the circuit (primarily for tests)."""
    global _failures, _open_until, _probe_inflight
    with _lock:
        _counts.update(dict.fromkeys(_counts, 0))
        _failures, _open_until, _probe_inflight = 0, 0.0, False


def _settings(cfg: dict | None) -> dict:
    effective = config.load_config() if cfg is None else cfg
    settings = {**config.DEFAULTS["imperium"], **effective.get("imperium", {})}
    base = settings["base_url"].rstrip("/")
    parsed = urllib.parse.urlsplit(base)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != "/harnesses/a0_scribe/v1"
    ):
        raise ValueError("expected the pinned a0_scribe harness URL")
    settings["base_url"] = base
    for key in ("timeout_seconds", "circuit_cooldown_seconds"):
        value = float(settings[key])
        if not math.isfinite(value) or value <= 0:
            raise ValueError("expected a positive duration")
        settings[key] = value
    threshold = settings["circuit_threshold"]
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
        raise ValueError("expected a positive integer threshold")
    if settings["priority"] not in {"low", "normal", "high"}:
        raise ValueError("invalid priority")
    return settings


def _allowed() -> bool:
    global _probe_inflight
    with _lock:
        if _open_until:
            if time.monotonic() < _open_until or _probe_inflight:
                _counts["circuit_open_skips"] += 1
                return False
            _probe_inflight = True
        return True


def _record(outcome: str, settings: dict) -> None:
    global _failures, _open_until, _probe_inflight
    with _lock:
        _counts[outcome] += 1
        _probe_inflight = False
        if outcome in {"ok", "busy"}:
            _failures, _open_until = 0, 0.0
        else:
            _failures += 1
            if _failures >= settings["circuit_threshold"]:
                _open_until = time.monotonic() + settings["circuit_cooldown_seconds"]


def _request(settings: dict, path: str, payload: dict | None = None) -> tuple[Any, str]:
    headers = {
        "Content-Type": "application/json",
        "X-Agent-Id": "a0_scribe",
        "X-Agent-Type": "scribe",
        "X-App-Id": "a0_scribe",
        "X-Priority": settings["priority"],
    }
    key = os.environ.get(settings["api_key_env"], "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(
        settings["base_url"] + path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=settings["timeout_seconds"]) as response:
            if response.status != 200:
                return None, "error"
            try:
                return json.loads(response.read().decode("utf-8")), "ok"
            except (ValueError, UnicodeError):
                return None, "invalid_response"
    except urllib.error.HTTPError as exc:
        with exc:
            if exc.code in {401, 403}:
                return None, "auth"
            if exc.code == 503:
                return None, "unavailable"
            if exc.code == 429:
                try:
                    if json.loads(exc.read(4096)).get("error", {}).get("code") == "queue_full":
                        return None, "busy"
                except (ValueError, AttributeError):
                    pass
            return None, "error"
    except TimeoutError:
        return None, "timeout"
    except urllib.error.URLError as exc:
        return None, "timeout" if isinstance(exc.reason, TimeoutError) else "unavailable"
    except OSError:
        return None, "unavailable"


def complete(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 512,
    temperature: float = 0.3,
    cfg: dict | None = None,
) -> str | None:
    """Attempt one completion; failures and busy lanes return None."""
    if not _allowed():
        return None
    settings = config.DEFAULTS["imperium"]
    text = None
    try:
        settings = _settings(cfg)
        response, outcome = _request(settings, "/chat/completions", {
            "model": "scribe",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "routing": {"role": "scribe", "task_type": "documentation", "local_only": True},
        })
        if outcome == "ok":
            try:
                text = response["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                pass
            if not isinstance(text, str) or not text.strip():
                text, outcome = None, "invalid_response"
    except Exception:
        outcome = "error"
    _record(outcome, settings)
    return text


def ping(cfg: dict | None = None) -> dict[str, Any]:
    """Check authenticated harness discovery without producing a model note.

    This diagnostic respects an open circuit but does not reset inference failures.
    """
    with _lock:
        if _open_until and (time.monotonic() < _open_until or _probe_inflight):
            return {"ok": False, "status": "circuit_open"}
    try:
        response, outcome = _request(_settings(cfg), "/models")
        if outcome == "ok":
            models = response.get("data") if isinstance(response, dict) else None
            if not isinstance(models, list) or not models or not all(
                isinstance(model, dict) and isinstance(model.get("id"), str) and model["id"]
                for model in models
            ):
                outcome = "invalid_response"
        return {"ok": outcome == "ok", "status": outcome}
    except Exception:
        return {"ok": False, "status": "error"}
