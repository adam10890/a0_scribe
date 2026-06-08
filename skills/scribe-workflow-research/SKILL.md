---
name: scribe-workflow-research
description: Use when a0_scribe sees searches, file reads, source inspection, documentation lookup, findings, or evidence gathering
---

# Scribe Workflow Research

## Activate On

Tags: `research`, `search`, `file_read`, `finding`.

## Capture

- active question
- source files or URLs
- findings
- confidence or uncertainty
- next action

## State Targets

- Workflow `state.active_question`
- Workflow `state.findings`
- Workflow `state.unresolved`
- Workflow `state.last_source_event`

## Review

Nudge if many sources are read without a finding, or if a finding is recorded
without a source.
