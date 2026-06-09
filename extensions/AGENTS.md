# DOX contract - a0_scribe/extensions

## Purpose

Agent Zero hook integration for booting the worker, observing tool calls,
injecting working state/nudges, and advisory enforcement.

## Ownership

- Extensions are integration shims; helper modules own business logic.
- Hooks must never block or break the ego's message/tool pipeline.

## Local Contracts

- Preserve command metadata from `agent.loop_data.current_tool.args` when
  extension arguments are incomplete.
- Keep observe/nudge/enforce behavior gated by config.

## Work Guidance

- Use narrow try/except boundaries around integration code.

## Verification

- Run `python -m py_compile` on touched extension files.
- Run focused state tracking tests when command metadata handling changes.

## Child DOX Index

No child AGENTS.md files yet.
