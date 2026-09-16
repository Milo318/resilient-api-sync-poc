from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from .mock_api import MockContactAPI, TransientAPIError


REQUIRED = {"external_id", "email", "first_name", "last_name", "company", "updated_at"}
SYNC_FIELDS = ("external_id", "email", "first_name", "last_name", "company", "phone", "updated_at")
MAPPING_FIELDS = SYNC_FIELDS[:-1]


def normalize_values(record: dict[str, object], fields: tuple[str, ...]) -> dict[str, str]:
    email = str(record["email"]).strip().lower()
    if "@" not in email:
        raise ValueError(f"Invalid email for {record.get('external_id', 'unknown')}")
    return {
        field: email if field == "email" else str(record.get(field, "")).strip()
        for field in fields
    }


@dataclass(frozen=True)
class AuditEvent:
    external_id: str
    action: str
    attempts: int
    idempotency_key: str
    reason: str


class SyncEngine:
    def __init__(self, source: MockContactAPI, target: MockContactAPI, max_attempts: int = 3) -> None:
        self.source = source
        self.target = target
        self.max_attempts = max_attempts

    @staticmethod
    def normalize(record: dict[str, object]) -> dict[str, object]:
        missing = REQUIRED - record.keys()
        if missing:
            raise ValueError(f"Missing required fields: {sorted(missing)}")
        return normalize_values(record, SYNC_FIELDS)

    @staticmethod
    def fingerprint(record: dict[str, object]) -> str:
        content = json.dumps(record, sort_keys=True, separators=(",", ":"))
        return sha256(content.encode()).hexdigest()[:16]

    def run(self) -> list[AuditEvent]:
        target_by_id = {
            str(record["external_id"]): self.normalize(record)
            for page in self.target.list_contacts()
            for record in page
        }
        events: list[AuditEvent] = []
        for page in self.source.list_contacts():
            for raw in page:
                try:
                    record = self.normalize(raw)
                except ValueError as exc:
                    events.append(AuditEvent(str(raw.get("external_id", "unknown")), "rejected", 0, "", str(exc)))
                    continue
                record_id = str(record["external_id"])
                key = f"contact:{record_id}:{self.fingerprint(record)}"
                existing = target_by_id.get(record_id)
                if existing == record:
                    events.append(AuditEvent(record_id, "skipped", 0, key, "target already matches source"))
                    continue
                attempts = 0
                while attempts < self.max_attempts:
                    attempts += 1
                    try:
                        action = self.target.upsert_contact(record, key)
                        target_by_id[record_id] = record
                        events.append(AuditEvent(record_id, action, attempts, key, "synchronized"))
                        break
                    except TransientAPIError as exc:
                        if attempts == self.max_attempts:
                            events.append(AuditEvent(record_id, "failed", attempts, key, str(exc)))
        return events


def summarize(events: list[AuditEvent]) -> dict[str, int]:
    actions = {action: 0 for action in ("created", "updated", "skipped", "replayed", "rejected", "failed")}
    for event in events:
        actions[event.action] = actions.get(event.action, 0) + 1
    actions["retried"] = sum(event.attempts > 1 for event in events)
    actions["total"] = len(events)
    return actions


def serialize_events(events: list[AuditEvent]) -> list[dict[str, object]]:
    return [asdict(event) for event in events]
