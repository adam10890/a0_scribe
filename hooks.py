"""Install hook for a0_scribe. Creates the runtime dir. No third-party deps."""
from __future__ import annotations

from pathlib import Path

PLUGIN_NAME = "a0_scribe"
RUNTIME_BASE = "usr/scribe"


def install(**kwargs):
    try:
        from helpers import files

        base = Path(files.get_abs_path(RUNTIME_BASE))
    except Exception:
        base = Path(RUNTIME_BASE)
    for rel in ("", "logs"):
        (base / rel).mkdir(parents=True, exist_ok=True)
    print(f"{PLUGIN_NAME}: runtime initialized at {base}")
    return 0
