---
name: scribe-workflow-verification
description: Use when a0_scribe sees tests, py_compile, lint, smoke checks, build output, pass/fail results, or completion claims requiring evidence
---

# Scribe Workflow Verification

## Activate On

Tags: `verification`, `test_result`, `compile_result`.

## Capture

- exact command
- pass/fail status
- failure summary
- affected files or modules
- follow-up action

## State Targets

- Workflow `state.latest_command`
- Workflow `state.latest_result`
- Workflow `state.unresolved`
- Workflow `state.last_result_event`

## Review

Nudge if the agent reports completion without fresh verification evidence, or if
a failure is not linked to a debugging workflow.
