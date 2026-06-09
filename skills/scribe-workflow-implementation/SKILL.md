---
name: scribe-workflow-implementation
description: Use when a0_scribe sees file changes, code edits, patches, behavior changes, or implementation progress that must be tracked
---

# Scribe Workflow Implementation

## Activate On

Tags: `implementation`, `file_change`, `code_change`.

## Capture

- files touched
- behavior changed
- assumptions
- pending verification
- next implementation step

## State Targets

- Workflow `state.current_files`
- Workflow `state.last_change_event`
- Root `working_set.current_focus`
- Root `working_set.next_action`

## Review

Nudge if code changes accumulate without a verification plan, or if scope changes
without updating the planning workflow.
