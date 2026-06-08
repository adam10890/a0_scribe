# a0_scribe — the Scribe (Super-Ego)

A background documentation & oversight layer for Agent Zero. A **separate, local
"scribe" model** — served by `a0_lmm_router` under a dedicated `scribe` role —
watches the chat agent and **auto-fills `a0_pen_paper` sessions in the
background**, on local GPU compute, without spending the chat/API budget and
without relying on the agent to take its own notes.

## The idea (id / ego / super-ego)

| Freud | Agent Zero | Role |
|---|---|---|
| Id | `utility` agent | fixed system drives (summaries, memory) |
| Ego | `chat` agent | acts and responds; the agent you talk to |
| **Super-Ego** | **`scribe` (this plugin)** | documents the work, keeps standards |

The chat agent often forgets to use Pen & Paper, and when it does, the notes cost
the expensive chat model. The scribe removes both problems: a cheap local model
documents the work automatically, so a session can be resumed later even after
the chat budget runs out.

## How it works

```
ego calls a tool
      │  tool_execute_after  (global hook, non-blocking)
      ▼
observation_bus  ── enqueue ──►  scribe_worker (daemon thread, continuous)
                                       │ debounce + batch
                                       ▼
                                 scribe_client → router role "scribe" (local GPU)
                                       │
                                       ▼
                                 a0_pen_paper session  (author="scribe")
```

- **Observer** (`tool_execute_after/_60_scribe_observe.py`): builds a compact
  observation per tool call and enqueues it. Never blocks the agent.
- **Worker** (`helpers/scribe_worker.py`): a single daemon thread that runs
  continuously while the plugin is enabled. It batches observations, asks the
  scribe model to summarize, and writes the note to Pen & Paper.
- **Client** (`helpers/scribe_client.py`): dependency-light sync HTTP to the
  `scribe` role, with fallback to the running router.
- **Writer** (`helpers/pen_paper_writer.py`): appends to the chat's focused
  session (or a per-chat `scribe_<id>` session), tagged `author="scribe"`.

## Requirements

- `a0_lmm_router` with the `scribe` role configured (slot `scribe_gpu`, port 8090,
  `gemma-4-8b`). See `docker/docker-compose.lmm.scribe.yml` in that plugin.
- `a0_pen_paper` (provides `sessions_store.ensure_session` / `append_section`).

## Enable & verify

1. Enable the plugin in Agent Zero (Plugin List).
2. Smoke-test the scribe role: click **Run** on the plugin, or:
   ```bash
   python usr/plugins/a0_scribe/execute.py
   ```
3. Run a normal chat that uses tools. A Pen & Paper session fills itself with
   entries authored by `scribe`. The ego's behavior is unchanged whether the
   scribe is on or off.

## Configuration

See `default_config.yaml`. Key knobs: `enabled`, `authority_level`,
`observe.debounce_seconds`, `budget.*`, `session.prefer_chat_focus`.

## Safety guardrails (תיקון או שובר)

- **Never affects the ego** — all scribe failures are swallowed; the agent runs
  identically with the scribe on or off.
- **Local & private** — runs on the local GPU via the router; no cloud/API.
- **Budget-capped** — per-chat runaway guard.
- **Transparent** — every entry is tagged `author="scribe"`, fully auditable.
- **Kill-switch** — `enabled: false` stops it instantly.

## Authority levels

All three are implemented (`authority_level` in `default_config.yaml`); the ego always
retains control:

- **observe** (default) — document only.
- **nudge** — advisory reminders injected into the ego's next prompt.
- **enforce** — soft workflow-deviation corrections injected before tools run (advisory,
  non-blocking).

Every nudge/deviation is also written to Pen & Paper (`author="scribe"`) for audit.

## Future development

See [docs/FUTURE.md](docs/FUTURE.md) — hard-blocking enforcement (opt-in) and the LMM
Router multi-container fleet orchestration that scribe will build on.
