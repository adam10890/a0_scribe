---
name: scribe-workflow-planning
description: Use when a0_scribe sees planning, architecture, design, options, scope changes, implementation plans, or decision-candidate events
---

# Scribe Workflow Planning

## Activate On

Tags: `planning`, `design`, `architecture`, `decision_candidate`.

## Capture

- goal and success criteria
- constraints and scope boundaries
- options considered
- chosen direction
- next action

## State Targets

- Root `working_set.current_focus`
- Root `working_set.next_action`
- Workflow `state.current_decision`
- Workflow `state.unresolved`

## Review

Nudge if work starts without a goal, if options are discussed without a
decision, or if the next action is empty after planning.
