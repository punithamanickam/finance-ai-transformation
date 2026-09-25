"""Provider-agnostic LLM interface with a numeric grounding validator.

The LLM is optional and has one job: rewrite the deterministic ANSWER paragraph in executive prose. It receives only
the evidence pack (the numbers already calculated) and must not introduce new figures. Every number in its output is
checked against the pack; any unsupported number causes the rewrite to be discarded and the deterministic answer kept.

Providers
* OfflineProvider (default without credentials): no rewrite.
* AnthropicProvider: Claude via the `anthropic` SDK when ANTHROPIC_API_KEY is set (never committed; see .env.example).
Add another provider by implementing `complete(system, prompt) -> str | None`.
"""
from __future__ import annotations

import os
import re

from src import settings

PROMPT_VERSION = "narrative-v1"
SYSTEM_PROMPT = (
    "You are the narrative writer for a CFO AI value dashboard. Rewrite the draft answer as two or three crisp executive "
    "sentences. Use ONLY numbers that appear in the evidence pack, written exactly as given. Do not calculate, round "
    "differently, infer or add any figure, date or percentage. Do not recommend decisions; you may say what management "
    "may wish to investigate. Distinguish realised (evidenced) value from expected (assumption-based) value."
)


class LLMProvider:
    name = "base"

    def complete(self, system: str, prompt: str) -> str | None:  # pragma: no cover - interface
        raise NotImplementedError


class OfflineProvider(LLMProvider):
    name = "offline"

    def complete(self, system: str, prompt: str) -> str | None:
        return None


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str = settings.LLM_MODEL):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model

    def complete(self, system: str, prompt: str) -> str | None:
        msg = self.client.messages.create(model=self.model, max_tokens=400, system=system,
                                          messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip() or None


def get_provider() -> LLMProvider:
    choice = settings.LLM_PROVIDER.lower()
    if choice == "offline" or (choice == "auto" and not os.getenv("ANTHROPIC_API_KEY")):
        return OfflineProvider()
    try:
        return AnthropicProvider()
    except Exception:
        return OfflineProvider()


_NUM_RE = re.compile(r"[-+]?\$?\d[\d,]*(?:\.\d+)?\s*(?:%|pp|[KMB]\b)?")


def numbers_in(text: str) -> set[str]:
    return {re.sub(r"[\s,+]", "", m.group(0)) for m in _NUM_RE.finditer(text) if re.search(r"\d", m.group(0))}


def validate_grounding(candidate: str, allowed_text: str) -> tuple[bool, list[str]]:
    """Every number in the candidate must appear verbatim (ignoring commas/spaces/sign) in the evidence pack."""
    allowed = numbers_in(allowed_text)
    allowed |= {a.lstrip("$") for a in allowed}
    bad = [n for n in numbers_in(candidate) if n not in allowed and n.lstrip("$") not in allowed and n.lstrip("-") not in allowed]
    return (not bad), bad


def rewrite(answer: str, pack: str, provider: LLMProvider | None = None) -> tuple[str, dict]:
    provider = provider or get_provider()
    meta = {"provider": provider.name, "prompt_version": PROMPT_VERSION, "used": False}
    if provider.name == "offline":
        return answer, meta
    try:
        out = provider.complete(SYSTEM_PROMPT, f"EVIDENCE PACK:\n{pack}\n\nDRAFT ANSWER:\n{answer}")
    except Exception as e:  # network or credential failure: fall back silently, record it
        meta["error"] = type(e).__name__
        return answer, meta
    if not out:
        return answer, meta
    ok, bad = validate_grounding(out, pack + "\n" + answer)
    meta.update({"validated": ok, "unsupported_numbers": bad})
    if not ok:
        return answer, meta
    meta["used"] = True
    return out, meta
