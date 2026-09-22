from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field


from .contracts import TransientAPIError


@dataclass
class MockContactAPI:
    """Deterministic stand-in for a paginated CRM API, explicitly for proof testing."""

    records: list[dict[str, object]]
    fail_first_attempt_for: set[str] = field(default_factory=set)
    attempts: dict[str, int] = field(default_factory=dict)
    idempotency_log: set[str] = field(default_factory=set)

    def list_contacts(self, page_size: int = 100) -> list[list[dict[str, object]]]:
        return [
            deepcopy(self.records[index : index + page_size])
            for index in range(0, len(self.records), page_size)
        ]

    def upsert_contact(self, record: dict[str, object], idempotency_key: str) -> str:
        record_id = str(record["external_id"])
        self.attempts[record_id] = self.attempts.get(record_id, 0) + 1
        if record_id in self.fail_first_attempt_for and self.attempts[record_id] == 1:
            raise TransientAPIError(f"Synthetic 503 for {record_id}")
        if idempotency_key in self.idempotency_log:
            return "replayed"
        self.idempotency_log.add(idempotency_key)
        for index, existing in enumerate(self.records):
            if existing["external_id"] == record["external_id"]:
                self.records[index] = deepcopy(record)
                return "updated"
        self.records.append(deepcopy(record))
        return "created"
