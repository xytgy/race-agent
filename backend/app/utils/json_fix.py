import json
import re


def ensure_valid_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"(\[.*\]|\{.*\})", text, re.S)
    if not match:
        raise ValueError("json_not_found")
    candidate = match.group(1)

    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    candidate = candidate.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(candidate)
    except Exception as exc:
        raise ValueError(f"json_repair_failed: {exc}")
