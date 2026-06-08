"""Config loader for a0_scribe.

Safe to import and run outside the Agent Zero runtime: falls back to the bundled
``default_config.yaml`` and then to hard defaults. Inside A0 it overlays the
plugin's per-agent/per-project config.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

PLUGIN_NAME = "a0_scribe"

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "authority_level": "observe",
    "model_role": "scribe",
    "observe": {
        "debounce_seconds": 4,
        "max_batch": 12,
        "max_queue": 1000,
        "ignore_tools": ["response", "scribe"],
    },
    "budget": {
        "max_calls_per_chat": 500,
        "max_tokens_per_call": 512,
        "temperature": 0.3,
    },
    "session": {
        "name_prefix": "scribe",
        "default_section": "execution_log",
        "prefer_chat_focus": True,
    },
    "feedback": {
        "max_pending_per_chat": 5,
        "inject_max_per_turn": 3,
    },
    "state": {
        "inject_working_state": True,
        "prompt_max_chars": 2500,
    },
    "runtime_dir": "usr/scribe",
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _read_default_yaml() -> dict:
    path = Path(__file__).resolve().parents[1] / "default_config.yaml"
    try:
        if path.exists() and yaml is not None:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def load_config(agent=None) -> dict[str, Any]:
    """Return the effective config (DEFAULTS < default_config.yaml < A0 config)."""
    cfg = _deep_merge(DEFAULTS, _read_default_yaml())
    try:
        from helpers.plugins import get_plugin_config

        a0_cfg = get_plugin_config(PLUGIN_NAME, agent=agent) or {}
        cfg = _deep_merge(cfg, a0_cfg)
    except Exception:
        pass
    return cfg
