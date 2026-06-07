"""Start the scribe background worker (agent_init).

agent_init is invoked synchronously, so this handler is a sync ``execute``. It
idempotently starts the daemon worker thread that drains the observation queue
continuously while the plugin is enabled. Loaded after a0_lmm_router's _10 init
(filename _30) so the fleet/router is set up first.

Placement: extensions/python/agent_init/_30_scribe_boot.py
"""
from __future__ import annotations

import logging

try:
    from helpers.extension import Extension
except ImportError:  # pragma: no cover
    from python.helpers.extension import Extension  # type: ignore

log = logging.getLogger("a0_scribe.boot")


def _config_provider() -> dict:
    try:
        from usr.plugins.a0_scribe.helpers.config import load_config

        return load_config()
    except Exception:
        return {}


class ScribeBoot(Extension):
    def execute(self, **kwargs) -> None:  # SYNC — agent_init is called sync
        try:
            cfg = _config_provider()
            if not cfg.get("enabled", True):
                return
            from usr.plugins.a0_scribe.helpers import scribe_worker

            scribe_worker.ensure_running(_config_provider)
        except Exception as exc:  # never break agent_init
            log.warning("a0_scribe boot skipped: %s", exc)
