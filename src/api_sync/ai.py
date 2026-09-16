from __future__ import annotations

import json
import os
import urllib.request


def suggest_field_mapping(source_schema: list[str], target_schema: list[str], samples: list[dict[str, object]]) -> dict[str, str]:
    """Stage 2 proposes mappings for unknown CRM schemas; mappings still require validation."""
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("Set LLM_API_KEY before using AI-assisted field mapping")
    base_url = os.environ.get("LLM_API_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "gpt-4.1-mini")
    request_data = {"source_schema": source_schema, "target_schema": target_schema, "samples": samples[:3]}
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Return JSON mapping source field names to target field names. Never transform values and never invent fields."},
            {"role": "user", "content": json.dumps(request_data, sort_keys=True)},
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        mapping = json.loads(json.load(response)["choices"][0]["message"]["content"])
    if not all(source in source_schema and target in target_schema for source, target in mapping.items()):
        raise ValueError(f"AI mapping failed schema validation: {mapping}")
    return mapping
