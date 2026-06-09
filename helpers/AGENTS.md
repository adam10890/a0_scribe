# DOX contract - a0_scribe/helpers

## Purpose

Scribe helper layer: event normalization, background worker, state prompt
rendering, model client, budgets, observation/feedback queues, and Pen & Paper
adapter code.

## Ownership

- `state_events.py` owns deterministic event tags and workflow routing.
- `scribe_worker.py` owns background processing and model patch application.
- `state_prompt.py` owns compact ego working-state rendering.
- `pen_paper_writer.py` is the only durable Pen & Paper write adapter.

## Local Contracts

- Model patches must not override deterministic routing fields.
- Failures must be swallowed or logged; helpers must not break the ego loop.
- Do not store runtime session state in this plugin.

## Work Guidance

- Keep pure state/event logic testable without Agent Zero runtime.
- Preserve fallback behavior when Pen & Paper or router integration is missing.

## Verification

- Run `python -m unittest tests.test_state_tracking -v` for state behavior.
- Run `python -m py_compile` on touched helper files.

## Child DOX Index

No child AGENTS.md files yet.
