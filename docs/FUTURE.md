# a0_scribe — Future development

## Authority phases (beyond v0.1 "observe")

v0.1 ships **observe** only: the scribe watches and documents. The design
supports two further authority levels, gated by `authority_level` in
`default_config.yaml` and always keeping the ego able to override:

- **nudge** — the scribe stages advisory reminders ("you never recorded the result
  of step 3") and injects them into the ego's *next* prompt via a
  `message_loop_prompts_after` extension. Advisory only.
- **enforce** — the scribe consults `a0_pen_paper`'s `WorkflowExecutor` to detect
  deviations from a registered workflow (research / debugging / validation) and
  injects a corrective note via a `tool_execute_before` extension. Soft
  enforcement first; hard blocking stays opt-in behind a toggle.

Each escalation must preserve the guardrails: local-only, budget-capped, fully
transparent (every action written to Pen & Paper with `author="scribe"`), and
overridable by the ego/user.

## Dependency: LMM Router multi-container fleet orchestration

The scribe currently runs as one dedicated container (`scribe_gpu`, gemma-4-8b,
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
