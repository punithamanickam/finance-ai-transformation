"""AI governance: append-only audit trail of every copilot interaction.

Each record captures: user query -> intent / metrics selected -> retrieved sources -> calculations -> LLM prompt
-> LLM response -> validation -> final answer, plus model, prompt version, engine version, confidence and timestamp.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from src import settings

AUDIT_LOG = settings.AUDIT_DIR / "audit_log.jsonl"


class AuditTrail:
    def __init__(self, user_query: str, session_id: str = "local"):
        self.record: dict[str, Any] = {
            "interaction_id": str(uuid.uuid4()),
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "user_query": user_query,
            "steps": [],
        }

    def step(self, name: str, **payload) -> None:
        self.record["steps"].append({"step": name, "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **payload})

    def set(self, **fields) -> None:
        self.record.update(fields)

    def finalize(self, final_answer: dict) -> dict:
        body = json.dumps(final_answer, sort_keys=True, default=str)
        self.record["final_answer"] = final_answer
        self.record["final_answer_sha256"] = hashlib.sha256(body.encode()).hexdigest()
        settings.AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(self.record, default=str) + "\n")
        return self.record


def read_audit_log(limit: int = 200) -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text().splitlines()[-limit:]
    return [json.loads(line) for line in reversed(lines) if line.strip()]
