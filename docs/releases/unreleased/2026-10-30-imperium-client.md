# Route Scribe through pinned Imperium

Type: minor
Area: client, worker, redaction
Version impact: minor (0.1.0 to 0.2.0)

## Summary

One local harness endpoint replaces direct host/chat fallback. Busy inference
skips safely; repeated failures open a bounded circuit with content-free counters.

## Migration

Install Imperium 0.13.0 first. Replace `model_role` with the documented `imperium`
settings, set the optional environment key, verify `/models`, then synthetic
inference. Preserve Pen & Paper data. See README for update/rollback instructions.

## Security and privacy

No new dependencies. Proxy settings and redirects cannot reroute content.
Private-key blocks and bare GitHub tokens are masked before queue/persistence.

## Validation

Hermetic unittest suite and changed-file py_compile; run the documented live
synthetic check separately. No installed Agent Zero hook proof is implied.
