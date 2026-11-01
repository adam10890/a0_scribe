# a0_scribe — the Scribe (Super-Ego)

A background documentation & oversight layer for Agent Zero. A **separate, local
"scribe" model** — served through a pinned local Imperium harness —
watches the chat agent and **auto-fills `a0_pen_paper` sessions in the
background**, on local compute, without spending the chat/API budget and
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
                                 scribe_client → Imperium /harnesses/a0_scribe/v1
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
  pinned Imperium harness, without host discovery, retries or fallback.
- **Writer** (`helpers/pen_paper_writer.py`): appends to the chat's focused
  session (or a per-chat `scribe_<id>` session), tagged `author="scribe"`.
- **State layer** (`helpers/state_events.py`, `helpers/state_prompt.py`):
  normalizes events into tags, activates workflow state files, builds the Scribe
  Context Envelope, and injects compact Pen & Paper working state back to the ego.
- **Skills** (`skills/`): agent-facing Scribe capability guidance for core
  guardrails, writing, state merge, review, handoff, recovery, and workflow modes.

## Requirements

- Standalone Imperium 0.13.0 or later, with a dedicated local slot and the
  `a0_scribe` harness pinned to it. The separate queue does not reserve hardware;
  evaluate the model and measure contention before enabling daily use.
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
- UI-published workflows may define custom activation tags. Scribe adds those
  tags when they are emitted as explicit evidence (`SCRIBE_TAGS: tag_name` or
  `STATE_DOX_TAGS: tag_name`) or as exact keywords in non-read-only activity.
  Source reads do not activate custom tags merely because a file contains the
  tag string.
- Reads of State-DOX artifacts (`state/events.jsonl`,
  `state/session_state.yaml`, `state/workflows/*`) are treated as audit events:
  they can be logged, but they do not replace the current active workflow focus.
- If a workflow declares a missing Scribe skill, Scribe falls back to
  `scribe-core` and records a warning in the active skill/workflow state.

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
- **Redacted** — common secret shapes (bearer tokens, `*_KEY`/`*TOKEN`/`*SECRET`/
  `*PASSWORD` values, `sk-…` keys, `AKIA…` ids) are masked before anything is
  queued, sent to the scribe model, or written to State-DOX.
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
python -m unittest tests.test_state_tracking tests.test_skill_contracts tests.test_review_findings -v
python -m py_compile helpers/state_events.py helpers/state_prompt.py helpers/scribe_worker.py helpers/pen_paper_writer.py extensions/python/tool_execute_after/_60_scribe_observe.py extensions/python/message_loop_prompts_after/_61_scribe_nudge.py
```

## Future development

See [docs/FUTURE.md](docs/FUTURE.md) — hard-blocking enforcement (opt-in) and the LMM
Router multi-container fleet orchestration that scribe will build on.

## Imperium configuration and migration (0.2.0)

The direct 8090-to-chat fallback and `model_role` setting are removed. Install
Imperium 0.13.0 first, then this client. Back up local plugin/config changes
before upgrading; preserve all Pen & Paper session data. Configure:

```yaml
imperium:
  base_url: http://host.docker.internal:9000/harnesses/a0_scribe/v1
  api_key_env: IMPERIUM_API_KEY
  timeout_seconds: 60
  priority: low
  circuit_threshold: 3
  circuit_cooldown_seconds: 120
```

Use `127.0.0.1` instead of `host.docker.internal` for a host-side worker. Verify
Docker reachability separately. The URL must select the dedicated harness;
compatibility model/role hints cannot escape its pin. Supply the router's bearer
key only through the named environment variable, never YAML. The client ignores
proxy environment/OS settings and rejects redirects. It sends local-only intent
and never sends notes to an alternate host when the target fails.

`429 queue_full` skips inference and resets the failure streak. Three consecutive
other failures open a 120-second circuit; no request leaves during cooldown.
A single probe after cooldown either recovers or reopens it. Success resets the
streak. `health()` exposes counters only; `reset()` clears process-local state.
`ping(cfg=...)` checks `/models` without producing a model note. The Run button
checks connectivity; it does not certify inference quality or installed hooks.
The worker always records deterministic events before model budget/network work.
Malformed/empty replies, auth errors and timeouts produce no fabricated note.

### Validate, update and rollback

Run from this plugin folder inside the `usr/plugins/a0_scribe` layout:

```powershell
python -m unittest tests.test_state_tracking tests.test_skill_contracts tests.test_review_findings tests.test_imperium_client -v
python execute.py
python -m pip list --outdated
# In an isolated environment after reviewing the update:
python -m pip install --upgrade PyYAML
```

There are no new dependencies: Python stdlib plus existing PyYAML. Review updates
in an isolated environment, upgrade only reviewed packages, then rerun these
checks and the same synthetic inference. CI uses both Windows and Linux with a
nested checkout; no live Agent Zero, model or Pen & Paper state is needed.
For rollback, stop the worker, restore the previous reviewed plugin/config and
restart its host. Keep the deterministic event history and session files.
Router rollback follows Imperium's own managed/source procedure. No data schema
migration or automatic daily activation is performed.

Ready-to-run Agent Zero check (in a disposable test chat):

> Run `python -c "print('SCRIBE_SYNTHETIC: 2 failed; no fix applied')"` as a tool.
> Inspect the Scribe-authored Pen & Paper event/note. It must preserve that outcome
> and must not claim tests passed or a fix was applied. Disconnect the Scribe
> endpoint for a second tool call; the deterministic event must still be recorded.

An isolated worker/model pilot does not prove the installed Agent Zero hooks;
record that evidence separately before daily activation.
