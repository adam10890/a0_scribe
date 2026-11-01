# Changelog

## [Unreleased]

### Changed

- Version 0.2.0 replaces direct model-host fallback with a single authenticated,
  pinned local Imperium harness. Router 0.13.0 is required before migration.
- Effective per-agent/project config is forwarded to the background client.

### Added

- Bounded HTTP timeout, busy skips, process-local failure counters and a circuit
  breaker, plus Windows/Linux hermetic client CI.

### Security

- Proxy inheritance and redirects are rejected; private-key blocks and GitHub
  token shapes are redacted before observation persistence and model requests.
- Deterministic event recording and untrusted-state framing remain intact.
