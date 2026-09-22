from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from .engine import SyncEngine, summarize
from .mock_api import MockContactAPI


def contact(index: int, updated: bool = False) -> dict[str, object]:
    return {
        "external_id": f"MOCK-{index:05d}",
        "email": f"contact{index}@example.test",
        "first_name": f"Demo{index}",
        "last_name": "Contact",
        "company": f"Synthetic Company {index % 37}",
        "phone": f"+49-000-{index:05d}",
        "updated_at": "2026-09-01T12:00:00Z" if not updated else "2026-08-01T12:00:00Z",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=Path("proof/benchmark.json"))
    args = parser.parse_args()
    if args.records < 1:
        parser.error("--records must be positive")
    source_records = [contact(index) for index in range(args.records)]
    target_records = [
        contact(index, updated=index % 2 == 0) for index in range(args.records // 2)
    ]
    initial_target_count = len(target_records)
    transient_failures = {f"MOCK-{index:05d}" for index in range(0, args.records, 97)}
    target = MockContactAPI(target_records, fail_first_attempt_for=transient_failures)
    engine = SyncEngine(MockContactAPI(source_records), target)
    started = perf_counter()
    events = engine.run()
    elapsed = perf_counter() - started
    replay_events = engine.run()
    summary = summarize(events)
    result = {
        "synthetic_data": True,
        "source_records": args.records,
        "initial_target_records": initial_target_count,
        **summary,
        "final_target_records": len(target.records),
        "processing_time_ms": round(elapsed * 1000, 3),
        "throughput_records_per_second": round(args.records / elapsed, 1),
        "failed_after_retries": summary["failed"],
        "replay_writes": sum(
            event.action in {"created", "updated"} for event in replay_events
        ),
        "idempotent_replay_percent": 100.0
        if all(event.action == "skipped" for event in replay_events)
        else 0.0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
