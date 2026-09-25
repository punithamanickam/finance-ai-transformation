"""Hallucination control: verify that every number in LLM-generated prose exists in the evidence pack.

A number in the narrative is accepted only if it matches (within display rounding) a value in the evidence
pack - reported facts, calculated metrics, scenario outputs, fiscal years, or numbers quoted in retrieved
management commentary. Anything else fails validation and the deterministic narrative is used instead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NUM_RE = re.compile(
    r"(?P<neg>[-−])?\$?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?P<suffix>%|pp|percentage points?|x\b|bn|billion|B\b|million|M\b|K\b|thousand)?",
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    passed: bool
    checked: int
    unsupported: list[str] = field(default_factory=list)
    notes: str = ""


def _candidates(tok: re.Match) -> list[float]:
    """Return the possible normalised interpretations of a number token (millions / ratio / raw)."""
    n = float(tok.group("num").replace(",", ""))
    if tok.group("neg"):
        n = -n
    s = (tok.group("suffix") or "").lower()
    if s in {"%", "pp", "percentage point", "percentage points"}:
        return [n / 100]
    if s in {"bn", "billion", "b"}:
        return [n * 1000]
    if s in {"million", "m"}:
        return [n]
    if s in {"k", "thousand"}:
        return [n, n / 1000]
    if s == "x":
        return [n]
    return [n, n / 100]


def allowed_values(pack: dict) -> list[float]:
    vals: list[float] = []

    def walk(o):
        if isinstance(o, bool):
            return
        if isinstance(o, (int, float)):
            vals.append(float(o))
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            for m in NUM_RE.finditer(o):
                vals.extend(_candidates(m))

    walk(pack)
    derived = []
    for v in vals:
        derived += [abs(v), v * 1000, v / 1000]
    return vals + derived


def _matches(c: float, allowed: list[float]) -> bool:
    for a in allowed:
        if a == 0 and abs(c) < 1e-9:
            return True
        if a != 0:
            rel = abs(c - a) / abs(a)
            # tolerance covers display rounding: 1 decimal on % (0.05pp), 1 decimal on $B, 2 on multiples
            if rel <= 0.006 or abs(c - a) <= 0.0006 or (abs(a) >= 1000 and abs(c - a) <= 50.5):
                return True
    return False


def validate_numbers(text: str, pack: dict) -> ValidationResult:
    allowed = allowed_values(pack)
    unsupported, checked = [], 0
    for tok in NUM_RE.finditer(text):
        raw = tok.group(0).strip()
        n = float(tok.group("num").replace(",", ""))
        if not tok.group("suffix") and (n < 10 and "." not in tok.group("num")):
            continue  # small integers ("three segments", "5 sentences") are not financial claims
        checked += 1
        if not any(_matches(c, allowed) for c in _candidates(tok)):
            unsupported.append(raw)
    return ValidationResult(passed=not unsupported, checked=checked, unsupported=unsupported,
                            notes="all numbers traced to evidence pack" if not unsupported else "unsupported numbers found")
