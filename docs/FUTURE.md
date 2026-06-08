# a0_scribe — Future development

## Authority phases — IMPLEMENTED

All three authority levels are now live (set `authority_level` in
`default_config.yaml`); the ego always retains the ability to override:

- **observe** (default) — watch and document only.
- **nudge** (Phase D) — the background worker emits an optional `NUDGE:` line; it is
  staged in `feedback_bus` and injected into the ego's *next* prompt via the
  `message_loop_prompts_after/_61_scribe_nudge.py` extension
  (`loop_data.extras_temporary`). Advisory only.
- **enforce** (Phase E) — the worker emits an optional `DEVIATION:` line (judged off
  the ego's critical path); `tool_execute_before/_55_scribe_enforce.py` injects it as a
  corrective `agent.hist_add_warning` before the next tool. SOFT enforcement — it
  advises, it does not block. Hard blocking remains opt-in for the future.

Guardrails preserved at every level: local-only, budget-capped, bounded feedback
(`feedback.max_pending_per_chat` / `inject_max_per_turn`), fully transparent (every
nudge/deviation is also written to Pen & Paper with `author="scribe"`), and overridable
by the ego/user. A future step could add true hard-blocking (veto a tool) behind an
explicit toggle. Per-chat active-workflow tracking now lives in Pen & Paper
State-DOX (`state/session_state.yaml` plus `state/workflows/*.yaml`); future
deviation detection should read that state rather than keeping a separate
workflow tracker.

## Dependency: LMM Router multi-container fleet orchestration

The scribe currently runs as one dedicated container (`scribe_gpu`, gemma-4-E4B,
2 parallel sequences). It will benefit directly from a planned `a0_lmm_router`
capability:

> **Multi-container fleet orchestration** — the router gains the ability to launch
> and control *multiple* llama.cpp containers, each hosting one or more models in
> parallel, and to scale them on demand. Roles (chat / utility / scribe / embedding
> and future roles) can then each get dedicated *or* pooled containers, sized to
> live load.

For the scribe specifically, this unlocks:
- **Per-chat / parallel scribe instances** — several concurrent chats each get a
  scribe worker backed by its own (or a pooled) container, instead of contending
  for one slot.
- **Elastic scaling** — spin scribe containers up under load and down when idle,
  so background documentation never starves the ego of GPU.
- **Zero manual compose** — the router manages container lifecycle, replacing the
  hand-run `docker-compose.lmm.scribe.yml`.

This is mirrored in the router's own future-dev note:
`usr/plugins/a0_lmm_router/docs/FUTURE_MULTI_CONTAINER.md`.
