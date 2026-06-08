---
name: scribe-review
description: Use when a0_scribe checks whether current work state satisfies workflow contracts, detects missing evidence, missing verification, blockers, or unsafe completion
---

# Scribe Review

## Goal

Compare current work against active workflow contracts.

## Review Checks

- Goal is present and still matches recent events.
- Active workflow has a phase and next action.
- Decisions have supporting evidence or source events.
- Code changes are followed by verification.
- Test failures have a debugging hypothesis or blocker.
- Completion claims have fresh verification evidence.

## Outputs

Use the weakest sufficient response:

1. update YAML state only
2. write a short Pen & Paper note
3. stage a `NUDGE`
4. stage a soft `DEVIATION`

Do not stage ego feedback for minor bookkeeping issues.

## Common Mistakes

- Do not enforce a workflow that is inactive.
- Do not block; scribe enforcement is advisory unless a future hard-block toggle is explicit.
- Do not treat absence of notes as failure if state is already complete.
