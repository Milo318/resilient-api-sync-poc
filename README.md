# Validated Contact Synchronization

Synchronize contact records with explicit validation, idempotency and an audit trail.

[![Quality](https://github.com/Milo318/resilient-api-sync-poc/actions/workflows/ci.yml/badge.svg)](https://github.com/Milo318/resilient-api-sync-poc/actions/workflows/ci.yml)

## What the current implementation guarantees

- Separate the transport interface from the in-memory demo adapter.
- Validate identities, contact fields, email shape and timezone-aware update timestamps.
- Reject duplicate target identities before writing; record duplicate source IDs as rejected.
- Retry transient failures with bounded exponential backoff and a stable idempotency key.
- Require nonempty, valid canary records before approving a schema mapping.
- Record created, updated, replayed, skipped, rejected and exhausted-retry outcomes.

## Run

Requires Python 3.11 or later.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m api_sync.cli
python -m api_sync.benchmark --records 1000 --output /tmp/sync-benchmark.json
```

## Scope and integration contract

The CLI uses two **in-memory mock APIs** populated from JSON. It writes target state and audit
files; it does not connect to an external CRM. Implement `ContactAPI` for a real system.
The target adapter must enforce idempotency durably, including retries after a lost receipt.
The demo keeps its idempotency log in memory only.

`configure_and_canary_sync` returns an approval/rollback decision for a proposed mapping;
it does not deploy or roll back a live integration. A structural canary cannot prove every
field's business meaning. Unknown mappings need representative source data and review.

Optional `suggest_field_mapping` uses `LLM_API_KEY` and optional `LLM_MODEL`/`LLM_API_URL`.
It validates one-to-one source/target fields. Permanent transport errors propagate rather
than being mislabeled as transient retries.

## Verification

```bash
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
```

CI runs these checks and a fresh deterministic benchmark on Python 3.11 and 3.13.
Tests include malformed inputs, known regression cases and mocked provider failures.
No credentials or live model calls are needed for the test suite. Provider responses have
size limits, JSON-object validation and bounded retries for transient failures.

## Benchmark evidence

All bundled datasets are synthetic. `proof/benchmark.json` records a deterministic demo
run; it does not establish performance on arbitrary customer data. The older
`proof/autonomous-benchmark.json`, case JSONL and portfolio image are **historical v1.0.0
artifacts**, not quality or accuracy guarantees for v1.1.0. Their archive-consistency test
does not execute the current controller or a live model.

Use the current regression suite to verify the current behavior. A fresh live-model
benchmark is optional and requires a configured Ollama instance; none is implied by a green
CI result. [Changes and compatibility](CHANGELOG.md).

Built by **Milo Geller** · [MIT licensed](LICENSE).
