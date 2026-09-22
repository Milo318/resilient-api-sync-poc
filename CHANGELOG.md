# Changelog

## 1.1.0

Validation and failure-handling update for validated contact synchronization.

- Separate the transport interface from the in-memory demo adapter.
- Validate identities, contact fields, email shape and timezone-aware update timestamps.
- Reject duplicate target identities before writing; record duplicate source IDs as rejected.
- Retry transient failures with bounded exponential backoff and a stable idempotency key.
- Require nonempty, valid canary records before approving a schema mapping.
- Record created, updated, replayed, skipped, rejected and exhausted-retry outcomes.

The documented runtime contracts now take precedence over historical benchmark cards.
Old live-model results remain preserved as historical evidence. See README for supported
input formats, output semantics and the checks to reproduce locally.
