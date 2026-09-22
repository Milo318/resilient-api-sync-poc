"""Transport boundary shared by real adapters and the in-memory example."""

from collections.abc import Iterable
from typing import Protocol


class TransientAPIError(RuntimeError):
    """A retryable transport failure; permanent failures must use another exception."""


class ContactAPI(Protocol):
    def list_contacts(self) -> Iterable[list[dict[str, object]]]: ...

    def upsert_contact(
        self, record: dict[str, object], idempotency_key: str
    ) -> str: ...
