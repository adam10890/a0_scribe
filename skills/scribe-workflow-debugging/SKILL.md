---
name: scribe-workflow-debugging
description: Use when a0_scribe sees errors, failed tests, tracebacks, repeated failed attempts, unexpected behavior, or debugging hypotheses
---

# Scribe Workflow Debugging

## Activate On

Tags: `tool_error`, `error_log`, `test_failure`, `unexpected_behavior`.

## Capture

- symptom
- reproduction command or trigger
- current hypothesis
- evidence gathered
- fix attempt
- verification result

## State Targets

- Workflow `state.current_hypothesis`
- Workflow `state.unresolved`
- Workflow `state.last_evidence_event`
- Root `working_set.next_action`

## Review

Nudge if the agent repeats a failed attempt, jumps to a fix without evidence, or
tries to conclude before verification passes.
