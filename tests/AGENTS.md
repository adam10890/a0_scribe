# DOX contract - a0_scribe/tests

## Purpose

Unit and contract tests for Scribe State-DOX behavior and skills.

## Ownership

- Tests should cover deterministic behavior without requiring a live Agent Zero
  runtime, router, or Pen & Paper service.

## Local Contracts

- Add focused tests for new event tags, workflow routing, state patch safety,
  or skill frontmatter rules.

## Work Guidance

- Prefer small fixture objects over live runtime dependencies.

## Verification

- Run `python -m unittest tests.test_state_tracking tests.test_skill_contracts -v`.

## Child DOX Index

No child AGENTS.md files yet.
