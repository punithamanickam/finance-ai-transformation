"""LLM provider abstraction. The model can be swapped without touching the calculation or retrieval layers.

* ``AnthropicProvider`` - Claude via the official Anthropic SDK (default model from LLM_MODEL).
* ``OfflineProvider``   - no model call; the copilot uses its deterministic narrative. Makes the prototype fully
                          runnable (and testable) without credentials.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from src import settings


@dataclass
class LLMResult:
    text: str | None
    provider: str
    model: str
    ok: bool
    error: str = ""
    usage: dict = field(default_factory=dict)
    stop_reason: str = ""


class LLMProvider:
    name = "base"
    model = "none"

    def generate(self, system: str, user: str) -> LLMResult:  # pragma: no cover - interface
        raise NotImplementedError


class OfflineProvider(LLMProvider):
    name = "offline"
    model = "deterministic-template"

    def generate(self, system: str, user: str) -> LLMResult:
        return LLMResult(text=None, provider=self.name, model=self.model, ok=False, error="offline mode - deterministic narrative used")


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str | None = None):
        import anthropic

        self.model = model or settings.LLM_MODEL
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(timeout=90.0, max_retries=2)

    def generate(self, system: str, user: str) -> LLMResult:
        a = self._anthropic
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"],
                extra_body={"fallbacks": "default"},
            )
        except a.RateLimitError as e:
            return LLMResult(None, self.name, self.model, False, f"rate limited: {e}")
        except a.APIStatusError as e:
            return LLMResult(None, self.name, self.model, False, f"API error {e.status_code}: {e.message}")
        except a.APIConnectionError as e:
            return LLMResult(None, self.name, self.model, False, f"connection error: {e}")
        if resp.stop_reason == "refusal":
            return LLMResult(None, self.name, resp.model, False, "model declined the request", stop_reason="refusal")
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
        return LLMResult(text or None, self.name, resp.model, bool(text), usage=usage, stop_reason=resp.stop_reason or "")


def get_provider(name: str | None = None) -> LLMProvider:
    name = (name or settings.LLM_PROVIDER).lower()
    if name == "offline":
        return OfflineProvider()
    if name in {"anthropic", "auto"}:
        has_creds = any(os.getenv(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"))
        if name == "anthropic" or has_creds:
            try:
                return AnthropicProvider()
            except Exception:  # SDK missing / misconfigured -> safe fallback
                return OfflineProvider()
    return OfflineProvider()
