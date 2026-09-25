"""Copilot: intent routing, hallucination controls, LLM guardrail, audit trail and response format."""
import json

import pytest

from src.copilot.copilot import CFOCopilot
from src.copilot.intent import detect_intent, parse_scenario
from src.copilot.llm import LLMProvider, LLMResult, OfflineProvider
from src.copilot.validation import validate_numbers

DEMO = {
    "What changed in the company's financial performance?": "biggest_changes",
    "Why did operating margin change?": "margin_drivers",
    "Which segment drove revenue growth?": "segment",
    "How did free cash flow change?": "cash_flow",
    "What are the biggest expense movements?": "expenses",
    "How much is the company investing in R&D?": "investment",
    "How has capex changed?": "metric_change",
    "What are the main financial risks disclosed by management?": "risks",
    "Show me the evidence behind this conclusion.": "show_source",
    "Run a scenario where revenue growth is 5 percentage points lower.": "scenario",
    "Which assumptions have the greatest sensitivity?": "sensitivity",
    "Show me exactly how you calculated that.": "show_calculation",
    "Explain the bridge between revenue growth and operating-income growth and show me the source for every number.": "profitability_bridge",
    "What will revenue be next year?": "forecast_request",
    "How much cash does the company have?": "cash_position",
    "Compare FY2026 with FY2024.": "comparison",
}


@pytest.mark.parametrize("q,intent", DEMO.items())
def test_intent_routing(q, intent):
    assert detect_intent(q, 2026).name == intent


def test_year_parsing():
    it = detect_intent("Compare FY2026 with FY2024.", 2026)
    assert (it.fiscal_year, it.prior_year) == (2026, 2024)


def test_scenario_parsing():
    s = parse_scenario("assume revenue growth is 5 percentage points lower while gross margin remains constant")
    assert s["deltas"] == {"revenue_growth": pytest.approx(-0.05)} and not s["overrides"]
    s = parse_scenario("what if R&D grows 20% and the tax rate is 21%")
    assert s["overrides"]["rd_growth"] == pytest.approx(0.20) and s["overrides"]["tax_rate"] == pytest.approx(0.21)


def test_numeric_validator():
    pack = {"key_numbers": [{"current": "$331.8B", "change": "+$50.1B (+17.8%)"}], "calculations": [{"value": "46.8%"}], "fiscal_year": 2026}
    assert validate_numbers("Revenue rose 17.8% to $331.8 billion in FY2026; operating margin was 46.8%.", pack).passed
    bad = validate_numbers("Revenue rose 19.2% to $340 billion.", pack)
    assert not bad.passed and len(bad.unsupported) == 2


class FakeLLM(LLMProvider):
    name, model = "fake", "fake-model"

    def __init__(self, text):
        self.text = text

    def generate(self, system, user):
        assert "EVIDENCE PACK" in user and "Use ONLY numbers" in system
        return LLMResult(self.text, self.name, self.model, True)


def test_llm_answer_used_only_when_numbers_validate(isolated_audit_log):
    good = CFOCopilot(provider=FakeLLM("Total revenue increased $50.1B (+17.8%) to $331.8B in FY2026."))
    r = good.ask("How did revenue change year over year?")
    assert r.answer_source == "llm" and r.validation["passed"]
    bad = CFOCopilot(provider=FakeLLM("Revenue grew 25% to $400 billion, and management expects 30% growth next year."))
    r2 = bad.ask("How did revenue change year over year?")
    assert r2.answer_source == "deterministic" and not r2.validation["passed"]
    assert "331.8" in r2.answer


def test_response_format_and_sources():
    r = CFOCopilot(provider=OfflineProvider()).ask("How did free cash flow change?")
    md = r.to_markdown()
    for section in ["**ANSWER**", "**KEY NUMBERS**", "**DRIVERS**", "**SOURCE**", "**CONFIDENCE:**", "**BASIS:**"]:
        assert section in md
    assert r.evidence.sources and all(str(s.url).startswith("https://www.sec.gov/") for s in r.evidence.sources)
    assert r.confidence in {"High", "Medium", "Low"}


def test_fact_and_inference_are_separated():
    r = CFOCopilot(provider=OfflineProvider()).ask("What changed in the company's financial performance?")
    bases = {s.basis for s in r.evidence.statements}
    assert {"calculated_analysis", "management_commentary"} <= bases
    for s in r.evidence.statements:
        if s.basis == "possible_interpretation":
            assert "may" in s.text or "could" in s.text or "not" in s.text


def test_hallucination_controls():
    cp = CFOCopilot(provider=OfflineProvider())
    assert cp.ask("What will revenue be next year?").status == "refused"
    r = cp.ask("What is the airspeed velocity of an unladen swallow?")
    assert r.status == "insufficient_evidence" and "could not find sufficient evidence" in r.answer


def test_scenario_is_labelled_illustrative():
    r = CFOCopilot(provider=OfflineProvider()).ask("Run a scenario where revenue growth is 5 percentage points lower.")
    assert "Illustrative scenario — not management guidance." in r.answer
    assert r.evidence.disclaimer


def test_follow_up_show_calculation_uses_previous_answer():
    cp = CFOCopilot(provider=OfflineProvider())
    cp.ask("Why did operating margin change?")
    r = cp.ask("Show me exactly how you calculated that.")
    assert r.intent == "show_calculation"
    assert any("formula" in s.text for s in r.evidence.statements)


def test_audit_log_records_full_chain(isolated_audit_log):
    cp = CFOCopilot(provider=FakeLLM("Operating income increased $26.7B to $155.2B."))
    cp.ask("Why did operating income increase?")
    rec = json.loads(isolated_audit_log.read_text().splitlines()[-1])
    steps = [s["step"] for s in rec["steps"]]
    assert steps == ["intent_detection", "retrieved_sources", "calculations", "llm_prompt", "llm_response", "validation"]
    for k in ["model", "prompt_version", "calculation_engine", "confidence", "user_query", "timestamp", "final_answer", "final_answer_sha256"]:
        assert rec[k]
