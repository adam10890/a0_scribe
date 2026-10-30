"""Standalone smoke test for a0_scribe (Plugin List "Run" button).

Checks the pinned Imperium harness model list. No model inference is requested, so
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
        f"authority={cfg.get('authority_level')} harness=a0_scribe"
    )
    result = scribe_client.ping(cfg=cfg)
    if result.get("ok"):
        print("OK - pinned harness model list is reachable; inference was not tested.")
        return 0
    print("FAIL - pinned harness discovery:", result.get("status"))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
