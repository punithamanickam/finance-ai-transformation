import re

import pytest

from src.agents.orchestrator import ask
from src.copilot.llm import LLMProvider, rewrite, validate_grounding
from src.governance import audit

DEMO = ["How much have we invested in AI?", "How much value has actually been realised?", "Why is realised value below expected value?",
        "What is driving AI cost growth?", "Show initiatives with significant budget variance.", "Which benefits rely heavily on assumptions?",
        "Explain the biggest ROI movement.", "What happens if utilisation increases to 80%?", "Which business units have the highest AI spend?",
        "Prepare a board-level AI investment briefing.", "Where is the AI money going?", "Why did AI ROI decline this quarter?",
        "Which initiatives have the largest budget variance?", "Which projects have benefits below plan?",
        "Show me all AI initiatives with more than $5M investment.", "What percentage of AI value is actually reflected in the P&L?",
        "Explain the $49.5M expected benefit.", "What happens if infrastructure utilisation increases from 63% to 80%?",
        "Prepare a CFO briefing for the board."]
EXPECTED_INTENT = {"Why did AI ROI decline this quarter?": "roi_movement", "Explain the biggest ROI movement.": "roi_movement",
                   "What happens if utilisation increases to 80%?": "scenario", "Show me all AI initiatives with more than $5M investment.": "data_query",
                   "Why is realised value below expected value?": "value_gap", "Prepare a CFO briefing for the board.": "briefing"}


@pytest.mark.parametrize("q", DEMO)
def test_demo_questions_get_structured_answers(q):
    r = ask(q, use_llm=False)
    assert r["intent"] not in ("fallback", "refused", "invalid")
    assert r["answer"] and r["key_drivers"] and r["numbers"] and r["evidence"]
    assert r["confidence"]["level"] in ("High", "Medium", "Low") and r["confidence"]["basis"]
    if q in EXPECTED_INTENT:
        assert r["intent"] == EXPECTED_INTENT[q]


def test_answer_numbers_are_grounded_in_the_numbers_pack():
    """Every $ figure in the deterministic answer appears in its numbers or drivers."""
    for q in DEMO[:8]:
        r = ask(q, use_llm=False)
        pack = " ".join(n["display"] for n in r["numbers"]) + " " + " ".join(r["key_drivers"]) + " " + r["answer"]
        for m in re.findall(r"\$\d[\d.,]*[KMB]", r["answer"]):
            assert m in pack


def test_roi_answer_names_largest_contributor_from_data(ctx):
    r = ask("Why did AI ROI fall this quarter?", use_llm=False)
    worst = ctx.portfolio.roi_movement()["initiatives"][0]["name"]
    assert worst in r["answer"] and any(d["kind"] == "evidence" for d in r["drilldown"])


def test_sql_and_destructive_requests_are_refused():
    assert ask("DROP TABLE users", use_llm=False)["intent"] == "refused"


def test_input_validation():
    assert ask("", use_llm=False)["intent"] == "invalid"
    assert ask("x" * 600, use_llm=False)["intent"] == "invalid"


def test_answers_are_audited_and_reproducible():
    a = ask("How much have we invested in AI?", use_llm=False)
    b = ask("How much have we invested in AI?", use_llm=False)
    assert a["result_sha256"] == b["result_sha256"] and a["audit_id"] != b["audit_id"]
    log = audit.read(5)
    assert log[0]["action"] == "copilot.query" and log[0]["result_sha256"] == b["result_sha256"]


def test_grounding_validator_rejects_invented_numbers():
    ok, bad = validate_grounding("Realised value is $30.3M, up 12% on plan.", "Realised value: $30.3M")
    assert not ok and "12%" in bad
    assert validate_grounding("Realised value is $30.3M.", "Realised value: $30.3M")[0]


class _Liar(LLMProvider):
    name = "test"

    def complete(self, system, prompt):
        return "We realised $99.9M of value."


class _Honest(LLMProvider):
    name = "test"

    def complete(self, system, prompt):
        return "Realised value stands at $30.3M."


def test_llm_rewrite_is_discarded_when_ungrounded():
    out, meta = rewrite("Realised value is $30.3M.", "Realised value: $30.3M", _Liar())
    assert out == "Realised value is $30.3M." and meta["validated"] is False
    out, meta = rewrite("Realised value is $30.3M.", "Realised value: $30.3M", _Honest())
    assert out == "Realised value stands at $30.3M." and meta["used"]
