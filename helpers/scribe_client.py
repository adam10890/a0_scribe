"""Sync HTTP client for the 'scribe' router role (served by a0_lmm_router).

Dependency-light (stdlib + optional yaml) so it can be imported and run
standalone (execute.py) and from the background worker thread. It reuses the
router's failover idea cheaply: try the dedicated scribe host first, then the
chat/router host (which serves the [scribe] preset alias). Never raises — all
failures return None.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

# Hard fallbacks if the router config can't be read.
_DEFAULT_HOSTS = {
    "scribe": "host.docker.internal:8090",
    "chat": "host.docker.internal:8080",
}


def _router_conf_paths() -> list[Path]:
    here = Path(__file__).resolve()
    root = here.parents[4]  # agent-zero-2
    paths: list[Path] = []
    env = os.environ.get("A0_LMM_ROUTER_CONFIG", "")
    if env:
        paths.append(Path(env))
    paths.append(root / "conf" / "llama_cpp_servers.yaml")
    paths.append(root / "usr" / "plugins" / "a0_lmm_router" / "conf" / "llama_cpp_servers.yaml")
    return paths


def _read_lmm_hosts() -> dict[str, str]:
    if yaml is None:
        return {}
    for path in _router_conf_paths():
        try:
            if not path.exists():
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                hosts = (data.get("global") or {}).get("lmm_hosts") or {}
                if isinstance(hosts, dict) and hosts:
                    return hosts
        except Exception:
            continue
    return {}


def candidate_base_urls() -> list[str]:
    hosts = _read_lmm_hosts()
    out: list[str] = []
    for role in ("scribe", "chat"):
        host = hosts.get(role) or _DEFAULT_HOSTS.get(role)
        if host:
            url = f"http://{host}/v1"
            if url not in out:
                out.append(url)
    for host in (_DEFAULT_HOSTS["scribe"], _DEFAULT_HOSTS["chat"]):
        url = f"http://{host}/v1"
        if url not in out:
            out.append(url)
    return out


def _post(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any] | None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def complete(
    messages: list[dict[str, str]],
    *,
    model: str = "scribe",
    max_tokens: int = 512,
    temperature: float = 0.3,
    timeout: float = 120.0,
) -> str | None:
    """Return the assistant text from the scribe role, or None on any failure."""
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    for base in candidate_base_urls():
        resp = _post(f"{base}/chat/completions", payload, timeout)
        if not resp:
            continue
        try:
            text = resp["choices"][0]["message"]["content"]
        except Exception:
            text = None
        if text:
            return text
    return None


def ping() -> dict[str, Any]:
    """Smoke-test helper used by execute.py."""
    candidates = candidate_base_urls()
    reply = complete([{"role": "user", "content": "ping"}], max_tokens=8, timeout=30)
    return {"ok": reply is not None, "candidates": candidates, "reply": reply}
