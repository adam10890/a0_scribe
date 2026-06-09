---
name: scribe-recovery
description: Use when a0_scribe state files are missing, malformed, stale, inconsistent with events.jsonl, or need reconstruction after a crash or bad model patch
---

# Scribe Recovery

## Goal

Restore valid State-DOX files without losing audit history.

## Recovery Order

1. Preserve existing files; do not delete state.
2. Read `events.jsonl` if valid.
3. Recreate missing `session_state.yaml` from defaults.
4. Recopy missing workflow YAML from templates.
5. Replay recent events into deterministic patches.
6. Record a recovery note in `workspace.json`.

## Malformed YAML

- Keep the bad file as evidence if the filesystem supports sidecar copies.
- Write a minimal valid replacement only after preserving the original content.
- Prefer recovering root state first; workflow states can be inactive until
  reactivated by tags.

## Common Mistakes

- Do not trust a model patch that caused the corruption.
- Do not infer decisions that are not present in events or notes.
