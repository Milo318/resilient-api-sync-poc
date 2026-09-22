from __future__ import annotations

from dataclasses import dataclass

from .engine import MAPPING_FIELDS, normalize_values

ALIASES = {
    "external_id": ("id", "contact_id", "customer_ref", "record_key", "external_key"),
    "email": ("email", "email_address", "mail", "primary_email", "contact_email"),
    "first_name": ("first_name", "given_name", "forename", "contact_first", "fname"),
    "last_name": ("last_name", "surname", "family_name", "contact_last", "lname"),
    "company": ("company", "organization", "account_name", "employer", "business"),
    "phone": ("phone", "mobile", "telephone", "phone_number", "contact_phone"),
}


@dataclass(frozen=True)
class MappingOutcome:
    mapping: dict[str, str]
    source: str
    approved: bool
    canary_records: int
    rollback_required: bool
    checks: tuple[str, ...]
    manual_approval_required: bool = False


def deterministic_mapping(source_fields: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for target, aliases in ALIASES.items():
        matches = [field for field in source_fields if field.lower() in aliases]
        if len(matches) == 1:
            result[target] = matches[0]
    return result


def transform_record(
    record: dict[str, object], mapping: dict[str, str]
) -> dict[str, str]:
    return normalize_values(
        {target: record[source] for target, source in mapping.items()}, MAPPING_FIELDS
    )


def _mapping_valid(mapping: dict[str, str], source_fields: list[str]) -> bool:
    return (
        set(mapping) == set(MAPPING_FIELDS)
        and len(set(mapping.values())) == len(MAPPING_FIELDS)
        and all(source in source_fields for source in mapping.values())
    )


def configure_and_canary_sync(
    source_fields: list[str],
    samples: list[dict[str, object]],
    ai_mapping: dict[str, object] | None,
) -> MappingOutcome:
    if (
        not isinstance(source_fields, list)
        or not source_fields
        or not all(isinstance(field, str) and field.strip() for field in source_fields)
        or len(set(source_fields)) != len(source_fields)
    ):
        return MappingOutcome(
            {}, "schema_rejected", False, 0, True, ("invalid_source_schema",)
        )
    proposal = ai_mapping if isinstance(ai_mapping, dict) else {}
    mapping = {
        target: source
        for target, source in proposal.items()
        if target in MAPPING_FIELDS and isinstance(source, str)
    }
    source = "ai"
    checks: list[str] = []
    deterministic = deterministic_mapping(source_fields)
    deterministic_complete = _mapping_valid(deterministic, source_fields)
    if not _mapping_valid(mapping, source_fields) or (
        deterministic_complete and mapping != deterministic
    ):
        mapping = deterministic
        source = "deterministic_self_repair"
        checks.append("invalid_or_conflicting_ai_mapping_repaired")
    canary_ok = bool(samples) and _mapping_valid(mapping, source_fields)
    transformed: list[dict[str, str]] = []
    if canary_ok:
        try:
            transformed = [transform_record(record, mapping) for record in samples]
            canary_ok = all(
                item["external_id"]
                and "@" in item["email"]
                and item["first_name"]
                and item["last_name"]
                for item in transformed
            )
        except (KeyError, ValueError, TypeError):
            canary_ok = False
    checks.extend(
        (
            "schema_allowlist_checked",
            "one_to_one_mapping_checked",
            "canary_values_validated",
        )
    )
    return MappingOutcome(
        mapping, source, canary_ok, len(transformed), not canary_ok, tuple(checks)
    )
