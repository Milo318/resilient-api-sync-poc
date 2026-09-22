from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import re
import time
from collections.abc import Callable
from datetime import datetime

from .contracts import ContactAPI, TransientAPIError


REQUIRED = {"external_id", "email", "first_name", "last_name", "company", "updated_at"}
SYNC_FIELDS = (
    "external_id",
    "email",
    "first_name",
    "last_name",
    "company",
    "phone",
    "updated_at",
)
MAPPING_FIELDS = SYNC_FIELDS[:-1]


def normalize_values(
    record: dict[str, object], fields: tuple[str, ...]
) -> dict[str, str]:
    if not isinstance(record, dict):
        raise ValueError("Contact must be an object")
    result = {}
    for field in fields:
        value = record.get(field, "")
        if not isinstance(value, str) or (field != "phone" and not value.strip()):
            raise ValueError(f"Contact field {field} must contain text")
        result[field] = value.strip()
    email = result["email"].lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Contact email is invalid")
    result["email"] = email
    if "updated_at" in fields:
        try:
            timestamp = datetime.fromisoformat(
                result["updated_at"].replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError("updated_at must be an ISO timestamp") from exc
        if timestamp.tzinfo is None:
            raise ValueError("updated_at requires a timezone")
    return result


@dataclass(frozen=True)
class AuditEvent:
    external_id: str
    action: str
    attempts: int
    idempotency_key: str
    reason: str


class SyncEngine:
    def __init__(
        self,
        source: ContactAPI,
        target: ContactAPI,
        max_attempts: int = 3,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        retry_delay: float = 0.1,
    ) -> None:
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or not 1 <= max_attempts <= 10
        ):
            raise ValueError("max_attempts must be between 1 and 10")
        if not math.isfinite(retry_delay) or retry_delay < 0:
            raise ValueError("retry_delay must be finite and nonnegative")
        self.source = source
        self.target = target
        self.max_attempts = max_attempts
        self.sleeper = sleeper
        self.retry_delay = retry_delay

    @staticmethod
    def normalize(record: dict[str, object]) -> dict[str, object]:
        if not isinstance(record, dict):
            raise ValueError("Contact must be an object")
        missing = REQUIRED - record.keys()
        if missing:
            raise ValueError(f"Missing required fields: {sorted(missing)}")
        return normalize_values(record, SYNC_FIELDS)

    @staticmethod
    def fingerprint(record: dict[str, object]) -> str:
        content = json.dumps(record, sort_keys=True, separators=(",", ":"))
        return sha256(content.encode()).hexdigest()[:16]

    def run(self) -> list[AuditEvent]:
        target_by_id = {}
        for page in self.target.list_contacts():
            for raw in page:
                record = self.normalize(raw)
                identifier = record["external_id"]
                if identifier in target_by_id:
                    raise ValueError("Target contains duplicate external IDs")
                target_by_id[identifier] = record
        seen_source_ids = set()
        events: list[AuditEvent] = []
        for page in self.source.list_contacts():
            for raw in page:
                try:
                    record = self.normalize(raw)
                except ValueError as exc:
                    events.append(
                        AuditEvent(
                            str(raw.get("external_id", "unknown"))
                            if isinstance(raw, dict)
                            else "unknown",
                            "rejected",
                            0,
                            "",
                            str(exc),
                        )
                    )
                    continue
                record_id = str(record["external_id"])
                if record_id in seen_source_ids:
                    events.append(
                        AuditEvent(
                            record_id, "rejected", 0, "", "duplicate source external ID"
                        )
                    )
                    continue
                seen_source_ids.add(record_id)
                key = f"contact:{record_id}:{self.fingerprint(record)}"
                existing = target_by_id.get(record_id)
                if existing == record:
                    events.append(
                        AuditEvent(
                            record_id,
                            "skipped",
                            0,
                            key,
                            "target already matches source",
                        )
                    )
                    continue
                attempts = 0
                while attempts < self.max_attempts:
                    attempts += 1
                    try:
                        action = self.target.upsert_contact(record, key)
                        if action not in {"created", "updated", "replayed"}:
                            raise ValueError("Target returned an invalid write receipt")
                        target_by_id[record_id] = record
                        events.append(
                            AuditEvent(record_id, action, attempts, key, "synchronized")
                        )
                        break
                    except TransientAPIError as exc:
                        if attempts == self.max_attempts:
                            events.append(
                                AuditEvent(record_id, "failed", attempts, key, str(exc))
                            )
                        else:
                            self.sleeper(
                                min(30, self.retry_delay * 2 ** (attempts - 1))
                            )
        return events


def summarize(events: list[AuditEvent]) -> dict[str, int]:
    actions = {
        action: 0
        for action in (
            "created",
            "updated",
            "skipped",
            "replayed",
            "rejected",
            "failed",
        )
    }
    for event in events:
        actions[event.action] = actions.get(event.action, 0) + 1
    actions["retried"] = sum(event.attempts > 1 for event in events)
    actions["total"] = len(events)
    return actions


def serialize_events(events: list[AuditEvent]) -> list[dict[str, object]]:
    return [asdict(event) for event in events]
