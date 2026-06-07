"""Standalone smoke test for a0_scribe (Plugin List "Run" button).

Resolves the scribe router role and pings it. Zero Agent Zero dependencies, so
it can be run directly:

    python usr/plugins/a0_scribe/execute.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    from usr.plugins.a0_scribe.helpers import config, scribe_client

    cfg = config.load_config()
    print(
        f"a0_scribe enabled={cfg.get('enabled')} "
        f"authority={cfg.get('authority_level')} role={cfg.get('model_role')}"
    )
    result = scribe_client.ping()
    print("scribe candidate URLs:", result.get("candidates"))
    if result.get("ok"):
        print("OK - scribe reply:", (result.get("reply") or "")[:120])
        return 0
    print("FAIL - scribe role did not respond. Is the fleet (or scribe container) up?")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
