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
  continuously while the plugin is enabled. It batches observations, records
  structured State-DOX events, asks the scribe model to summarize or patch state,
  and writes notes to Pen & Paper.
- **Client** (`helpers/scribe_client.py`): dependency-light sync HTTP to the
  `scribe` role, with fallback to the running router.
- **Writer** (`helpers/pen_paper_writer.py`): appends to the chat's focused
  session (or a per-chat `scribe_<id>` session), tagged `author="scribe"`.
- **State layer** (`helpers/state_events.py`, `helpers/state_prompt.py`):
  normalizes events into tags, activates workflow state files, builds the Scribe
  Context Envelope, and injects compact Pen & Paper working state back to the ego.
- **Skills** (`skills/`): agent-facing Scribe capability guidance for core
  guardrails, writing, state merge, review, handoff, recovery, and workflow modes.

## Requirements

- `a0_lmm_router` with the `scribe` role configured (slot `scribe_gpu`, port 8090,
  `gemma-4-E4B`). See `docker/docker-compose.lmm.scribe.yml` in that plugin.
- `a0_pen_paper` (provides `sessions_store.ensure_session` / `append_section`).

## Enable & verify

1. Enable the plugin in Agent Zero (Plugin List).
2. Smoke-test the scribe role: click **Run** on the plugin, or:
   ```bash
   python usr/plugins/a0_scribe/execute.py
   ```
3. Run a normal chat that uses tools. A Pen & Paper session fills itself with
   entries authored by `scribe`. The scribe is never on the ego's critical path:
   it never blocks or alters tool execution. With `state.inject_working_state`
   enabled (the default), the ego also receives a compact, read-only working-state
   prompt.

## Configuration

See `default_config.yaml`. Key knobs: `enabled`, `authority_level`,
`observe.debounce_seconds`, `budget.*`, `session.prefer_chat_focus`, and
`state.inject_working_state`.

## State-DOX model

The scribe does not track raw chain-of-thought or a full transcript. It writes
compact events to the active Pen & Paper session's `state/events.jsonl`, keeps
`state/session_state.yaml` as the root operational state, and updates active
workflow YAML files copied from Pen & Paper templates. The ego receives only a
compact working-state prompt, not raw events.

Runtime layout inside the resolved Pen & Paper workspace:

```text
state/
├── events.jsonl                 # append-only compact event audit
├── session_state.yaml           # current session-level working truth
└── workflows/
    ├── planning.yaml
    ├── implementation.yaml
    ├── debugging.yaml
    ├── verification.yaml
    └── research.yaml
```

Current workflow activation is deterministic before any model patch is applied:

- `active_workflows` is the current focus selected from the newest meaningful
  event. It is not an append-only history.
- `events.jsonl` is the durable evidence history.
- Workflow YAML files are mutable live copies of Pen & Paper templates, linked
  to matching `skills/scribe-workflow-*` guidance.
- Model-authored `session_patch` cannot override deterministic routing fields
  such as `active_workflows`, event ids, or inactive workflow state.

## Event semantics

Event tags are command/outcome-aware:

- Research/file reads activate `research` only.
- `python -m py_compile`, `pytest`, and `unittest` activate `verification`.
- Failed verification commands also activate `debugging`.
- Read-only source inspection output is treated as observed content, not tool
  outcome. A file that contains words such as `Exception`, `failed`, or
  `tool_error` must not trigger debugging unless the command itself failed or
  was an explicit verification/test command.

The observer preserves tool command metadata from
`agent.loop_data.current_tool.args` because Agent Zero after-tool extensions do
not reliably receive `tool_args`. This is critical for successful commands that
produce little or no stdout, such as a passing `py_compile`.

## Session routing

Scribe writes into the Pen & Paper workspace resolved for the current chat:

1. Explicit Pen & Paper chat focus.
2. Existing user-named workspace for the same `chat_id`.
3. Automatic fallback `scribe_<chat_id>`.

Only the exact fallback name is considered automatic. User workspaces may also
start with `scribe_`, such as `scribe_semantic_regression_005`.

## Safety guardrails (תיקון או שובר)

- **Never blocks the ego** — all scribe failures are swallowed and no scribe step
  is on the ego's critical path. Tool execution runs identically with the scribe
  on or off. When `state.inject_working_state` is on (the default), a compact
  read-only working-state block is added to the ego's prompt.
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

## Development checks

From `usr/plugins/a0_scribe/`:

```bash
python -m unittest tests.test_state_tracking tests.test_skill_contracts -v
python -m py_compile helpers/state_events.py helpers/state_prompt.py helpers/scribe_worker.py helpers/pen_paper_writer.py extensions/python/tool_execute_after/_60_scribe_observe.py
```

## Future development

See [docs/FUTURE.md](docs/FUTURE.md) — hard-blocking enforcement (opt-in) and the LMM
Router multi-container fleet orchestration that scribe will build on.
