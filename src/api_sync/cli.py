from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import SyncEngine, serialize_events, summarize
from .mock_api import MockContactAPI


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronize contacts with retries, validation, and idempotency."
    )
    parser.add_argument(
        "--source", type=Path, default=Path("data/mock/source_contacts.json")
    )
    parser.add_argument(
        "--target", type=Path, default=Path("data/mock/target_contacts.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("output/synced_contacts.json")
    )
    parser.add_argument("--audit", type=Path, default=Path("output/audit_log.json"))
    args = parser.parse_args()
    source_records = json.loads(args.source.read_text(encoding="utf-8"))
    target_records = json.loads(args.target.read_text(encoding="utf-8"))
    failures = {
        str(item["external_id"])
        for index, item in enumerate(source_records)
        if index % 7 == 0
    }
    source = MockContactAPI(source_records)
    target = MockContactAPI(target_records, fail_first_attempt_for=failures)
    events = SyncEngine(source, target).run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(target.records, indent=2) + "\n", encoding="utf-8"
    )
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(
        json.dumps(serialize_events(events), indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summarize(events), indent=2))


if __name__ == "__main__":
    main()
