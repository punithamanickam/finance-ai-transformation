"""Append-only audit log (database table `audit_log`).

Each record: timestamp, user, role, action, a JSON detail (question, intent, agent, evidence ids, SQL, LLM use,
validation result) and the SHA-256 of the response body, so any answer can be shown to be reproducible: re-running
the same question on the same data produces the same hash.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import insert, select

from src.db import schema
from src.db.database import ensure_base_database


def content_hash(payload) -> str:
    body = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def record(user_id: str, role: str, action: str, detail: dict, result=None) -> int:
    engine = ensure_base_database()
    with engine.begin() as conn:
        res = conn.execute(insert(schema.audit_log).values(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"), user_id=user_id, role=role, action=action,
            detail=json.dumps(detail, default=str), result_sha256=content_hash(result) if result is not None else None))
        return int(res.inserted_primary_key[0])


def read(limit: int = 200) -> list[dict]:
    engine = ensure_base_database()
    with engine.connect() as conn:
        rows = conn.execute(select(schema.audit_log).order_by(schema.audit_log.c.id.desc()).limit(limit)).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = json.loads(d["detail"])
        except Exception:
            pass
        out.append(d)
    return out
