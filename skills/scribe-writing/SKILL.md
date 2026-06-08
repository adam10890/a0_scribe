---
name: scribe-writing
description: Use when a0_scribe needs to write human-readable Pen & Paper audit notes from compact events, findings, decisions, results, nudges, or deviations
---

# Scribe Writing

## Goal

Write short audit notes that help a future agent resume the work.

## Write When

- a finding changes what the agent knows
- a decision changes direction
- a verification command passes or fails
- a blocker appears or is resolved
- a workflow deviation or nudge is staged

## Write Shape

Use one Pen & Paper section:

| Event | Section |
|---|---|
| evidence or discovery | `findings` |
| command result | `results` |
| chosen direction | `decisions` |
| corrective reminder | `notes` |
| workflow deviation | `backtrack` |
| ordinary tool progress | `execution_log` |

Keep notes to 2-5 sentences. Include command names or file names when useful.
Do not paste full logs unless the failure text itself is the finding.

## Common Mistakes

- Do not duplicate the same note if `events.jsonl` already shows no state change.
- Do not invent unstated rationale.
- Do not write raw transcript snippets as notes.
