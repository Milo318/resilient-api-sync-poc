from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time
import urllib.request

from .autonomy import TARGET_FIELDS, configure_and_canary_sync


@dataclass(frozen=True)
class SchemaCase:
    case_id: str
    source_fields: list[str]
    samples: list[dict[str, object]]
    truth: dict[str, str]


VARIANTS = [
    ("id", "email", "first_name", "last_name", "company", "phone"),
    ("contact_id", "email_address", "given_name", "surname", "organization", "mobile"),
    ("customer_ref", "mail", "forename", "family_name", "account_name", "telephone"),
    ("record_key", "primary_email", "contact_first", "contact_last", "employer", "phone_number"),
    ("external_key", "contact_email", "fname", "lname", "business", "contact_phone"),
]


def generate_cases(count: int) -> list[SchemaCase]:
    cases: list[SchemaCase] = []
    for index in range(count):
        fields = VARIANTS[index % len(VARIANTS)]
        truth = dict(zip(TARGET_FIELDS, fields))
        samples = []
        for item in range(5):
            canonical = {
                "external_id": f"MOCK-{index:03d}-{item}", "email": f"Person{item}@Example.Test",
                "first_name": f"Demo{item}", "last_name": "Contact", "company": f"Synthetic Co {index}", "phone": f"+49-000-{index:03d}{item}",
            }
            samples.append({truth[target]: value for target, value in canonical.items()})
        cases.append(SchemaCase(f"SCHEMA-{index:03d}", list(fields), samples, truth))
    return cases


def ask_ollama(batch: list[SchemaCase], model: str, url: str) -> tuple[dict[str, dict[str, object]], dict[str, int]]:
    items = [{"case_id": case.case_id, "source_fields": case.source_fields, "sample": case.samples[0]} for case in batch]
    prompt = (
        "Map every source schema to canonical CRM fields. Return JSON with results array. Each item needs case_id and mapping. "
        f"mapping keys must be exactly {list(TARGET_FIELDS)} and values must be source field names. Do not omit cases.\n\n" + json.dumps(items)
    )
    payload = {"model": model, "stream": False, "format": "json", "keep_alive": "10m", "options": {"temperature": 0, "num_predict": 1600}, "messages": [{"role": "system", "content": "You map API schemas precisely. Output JSON only."}, {"role": "user", "content": prompt}]}
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        raw = json.load(response)
    parsed = json.loads(raw["message"]["content"])
    results = parsed.get("results", parsed if isinstance(parsed, list) else [])
    return {str(item.get("case_id")): item.get("mapping", {}) for item in results if isinstance(item, dict)}, {"prompt_tokens": int(raw.get("prompt_eval_count", 0)), "completion_tokens": int(raw.get("eval_count", 0))}


def run(count: int, model: str, url: str, batch_size: int) -> tuple[dict[str, object], list[dict[str, object]]]:
    cases = generate_cases(count)
    started = time.perf_counter()
    proposals: dict[str, dict[str, object]] = {}
    prompt_tokens = completion_tokens = 0
    for index in range(0, count, batch_size):
        result, usage = ask_ollama(cases[index:index + batch_size], model, url)
        proposals.update(result)
        prompt_tokens += usage["prompt_tokens"]
        completion_tokens += usage["completion_tokens"]
    rows: list[dict[str, object]] = []
    for case in cases:
        proposal = proposals.get(case.case_id)
        direct = proposal == case.truth
        outcome = configure_and_canary_sync(case.source_fields, case.samples, proposal)
        correct = outcome.mapping == case.truth
        rows.append({"case_id": case.case_id, "ai_direct_pass": direct, "decision_source": outcome.source, "canary_records": outcome.canary_records, "rollback_required": outcome.rollback_required, "truth_match": correct, "approved": outcome.approved and correct})
    elapsed = time.perf_counter() - started
    direct = sum(row["ai_direct_pass"] for row in rows)
    approved = sum(row["approved"] for row in rows)
    summary = {
        "benchmark": "autonomous_api_mapping_v1", "live_model": True, "model": model,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "synthetic_data": True,
        "benchmark_cases": count, "minimum_required_cases": 100,
        "ai_direct_passed": direct, "ai_direct_pass_rate_percent": round(direct / count * 100, 2),
        "final_approved": approved, "approval_rate_percent": round(approved / count * 100, 2),
        "required_approval_rate_percent": 95.0, "acceptance_gate_passed": count >= 100 and approved / count > 0.95,
        "manual_approvals_required": 0, "automatic_self_repairs": sum(row["decision_source"] == "deterministic_self_repair" for row in rows),
        "canary_records_validated": sum(int(row["canary_records"]) for row in rows),
        "rollbacks_required": sum(bool(row["rollback_required"]) for row in rows),
        "elapsed_seconds": round(elapsed, 3), "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "case_generator_sha256": sha256(json.dumps([case.truth for case in cases], sort_keys=True).encode()).hexdigest(),
    }
    return summary, rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=120)
    parser.add_argument("--model", default="granite4.1:3b")
    parser.add_argument("--url", default="http://localhost:11434/api/chat")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("proof/autonomous-benchmark.json"))
    parser.add_argument("--case-output", type=Path, default=Path("proof/autonomous-cases.jsonl"))
    args = parser.parse_args()
    if args.cases < 100:
        raise SystemExit("At least 100 cases are required")
    summary, rows = run(args.cases, args.model, args.url, args.batch_size)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    args.case_output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["acceptance_gate_passed"]:
        raise SystemExit("Acceptance gate failed")


if __name__ == "__main__":
    main()
