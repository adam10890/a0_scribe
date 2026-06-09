# DOX contract - a0_scribe/skills

## Purpose

Agent-facing Scribe capability guidance for core behavior, writing, handoff,
recovery, review, state merge, and workflow modes.

## Ownership

- Skill frontmatter stays limited to `name` and `description`.
- Workflow skills must align with Pen & Paper State-DOX template metadata.

## Local Contracts

- Do not introduce raw chain-of-thought capture.
- Operation skills and workflow skills remain separate.

## Work Guidance

- Update `tests/test_skill_contracts.py` when skill contract rules change.

## Verification

- Run `python -m unittest tests.test_skill_contracts -v`.

## Child DOX Index

No child AGENTS.md files yet.
