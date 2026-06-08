# DOX contract — a0_scribe

## Purpose

Background Scribe / super-ego plugin for Agent Zero. It observes compact chat
events, maintains Pen & Paper State-DOX files, writes auditable notes, and can
inject advisory working-state context back into the ego.

## Ownership

- This folder is plugin source for the live Agent Zero install.
- Do not store runtime session data in this plugin. Runtime state belongs in the
  resolved `a0_pen_paper` session under `state/`.
- Keep model calls local-only through the `a0_lmm_router` `scribe` role.
- Scribe failures must never break the ego's tool or message loop.

## Local Contracts

- `helpers/state_events.py` owns event normalization, tags, workflow activation,
  and Scribe Context Envelope construction.
- Event tags must be command/outcome-aware. Do not activate workflows only
  because inspected file contents, paths, or skill names contain words like
  `test`, `error`, `design`, or `verification`.
- Read-only source/file inspection output is observed content, not a tool
  outcome signal. Do not trigger debugging from words like `Exception`,
  `tool_error`, or `failed` inside inspected source unless the command itself is
  an explicit verification/test command.
- When digest output contains `SIGNALS:` excerpts, preserve command context from
  the pre-signal text. Signal excerpts from inspected source code must not
  replace the command metadata used for read-only/verification classification.
- Tool observation must preserve command metadata. In `tool_execute_after`, the
  canonical source is `agent.loop_data.current_tool.args`; successful shell
  commands can produce no meaningful stdout. Keep fallbacks for
  `response.additional` / `response.kvps` when available.
- `session_state.yaml` `active_workflows` represents the current operational
  focus from the newest meaningful event, not an append-only history. Durable
  evidence history belongs in `events.jsonl` and per-workflow YAML files.
- Model-authored `session_patch` and `workflow_patches` must not override
  deterministic workflow routing. `active_workflows`, event ids, and inactive
  workflow state are owned by `state_events.py` + `scribe_worker.py`.
- `helpers/state_prompt.py` owns compact working-state prompt rendering for ego
  injection; it must not include raw `events.jsonl`.
- `helpers/scribe_worker.py` owns the background worker, model prompting, and
  applying state patches.
- `helpers/pen_paper_writer.py` is the adapter to `a0_pen_paper`; do not bypass
  Pen & Paper storage for durable session state.
- Session resolution must prefer explicit chat focus, then an existing
  user-named workspace for the same `chat_id`, then the automatic
  `scribe_<chat_id>` fallback. Treat only the exact fallback name as
  automatic; user test/workflow names may also start with `scribe_`.
- `skills/` owns agent-facing Scribe capability guidance. Keep frontmatter to
  `name` and `description`, and keep operation skills separate from workflow
  skills.
- Workflow skills must stay aligned with `a0_pen_paper`
  `data/workflow_state_templates/*` `scribe.skill` metadata.
- Agent-facing extensions must stay non-blocking and swallow failures.

## Verification

- Run `python -m unittest tests.test_state_tracking -v`.
- Run `python -m unittest tests.test_skill_contracts -v` when changing Scribe
  skills.
- Run `python -m py_compile` on touched Python files.
- When changing Pen & Paper state integration, also run the corresponding
  `a0_pen_paper` state tests.
- After Scribe behavior changes, include a ready-to-run Agent Zero test prompt
  in the user-facing handoff.

## Child DOX Index

No child AGENTS.md files yet.
