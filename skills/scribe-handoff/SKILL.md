---
name: scribe-handoff
description: Use when a0_scribe prepares compact resume state before context compression, session handoff, budget exhaustion, restart, or user-requested summary
---

# Scribe Handoff

## Goal

Produce enough state for the ego or a future agent to resume without the raw
chat transcript.

## Handoff Must Include

- current goal
- current focus
- active workflows and phases
- key decisions
- unresolved blockers
- latest verification status
- exact next action

## Source Order

1. `session_state.yaml`
2. active `workflows/*.yaml`
3. recent `events.jsonl`
4. `workspace.json` notes only if YAML is incomplete

## Output

Prefer a compact YAML patch or state block. Avoid prose unless the user asked
for a human-readable handoff.
