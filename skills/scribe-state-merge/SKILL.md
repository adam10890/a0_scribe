---
name: scribe-state-merge
description: Use when a0_scribe updates session_state.yaml or workflow YAML from event tags, model patches, verification results, blockers, or next-action changes
---

# Scribe State Merge

## Goal

Keep YAML state compact, current, and editable by humans.

## Merge Rules

- Prefer replacement over append for current fields like `current_focus` and
  `next_action`.
- Append only durable lists: new decisions, open questions, unresolved blockers.
- Remove or mark resolved stale items when later events supersede them.
- Preserve unrelated keys and human edits.
- Keep workflow state in the workflow file, not in root session state.

## Root State

Update `session_state.yaml` for:

- current goal/status
- current focus
- next action
- active workflow index
- open questions
- high-level tags
- last event id

## Workflow State

Update `workflows/<id>.yaml` for workflow-specific phase, evidence, unresolved
items, and completion requirements.

## Safety

If a model patch is malformed, reject it and keep the deterministic event patch.
Never erase the state file to recover from a bad patch.
