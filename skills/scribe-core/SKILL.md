---
name: scribe-core
description: Use when maintaining a0_scribe Pen & Paper State-DOX behavior, event tagging, compact working state, or super-ego guardrails
---

# Scribe Core

## Core Rule

Maintain durable working state without flooding context.

Do not capture raw chain-of-thought. Capture reasoning signals: intent,
decision, assumption, finding, risk, blocker, verification result, next action.

## Operating Model

- Treat Pen & Paper state as the operational truth.
- Write raw compact events to `state/events.jsonl`.
- Merge current truth into `state/session_state.yaml`.
- Update only active `state/workflows/*.yaml`.
- Keep `workspace.json` for human-readable audit notes.
- Never let scribe failures break the ego's message or tool loop.

## State Inputs

Use only observable artifacts:

- user-visible messages
- tool names, args digests, and result digests
- test/compile outcomes
- explicit plans, decisions, warnings, and errors
- Pen & Paper state files

## Common Mistakes

| Mistake | Correct behavior |
|---|---|
| Summarizing every event | Merge only state-changing facts |
| Treating transcript as state | Treat YAML state as current truth |
| Recording hidden reasoning | Record explicit reasoning signals only |
| Appending forever | Resolve, replace, and compact stale state |
