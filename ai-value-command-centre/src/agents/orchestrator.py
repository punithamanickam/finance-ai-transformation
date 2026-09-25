"""Agent / orchestration layer for the AI CFO Copilot.

question -> input validation -> intent routing -> specialist agent (deterministic engines) -> optional LLM narrative
(grounding-validated) -> structured response -> audit log.
"""
from __future__ import annotations

import re
from functools import lru_cache

from src.agents.base import Context
from src.agents.benefits_agent import BenefitsAgent
from src.agents.finance_analyst import FinanceAnalystAgent
from src.agents.portfolio_analyst import PortfolioAnalystAgent
from src.agents.reporting_agent import ReportingAgent
from src.agents.research_agent import ResearchAgent
from src.agents.scenario_agent import ScenarioAgent
from src.copilot import llm
from src.copilot.response import CopilotResponse
from src.governance import audit
from src.query.semantic_layer import FORBIDDEN, QueryRefused
from src.security.auth import Principal

HPE_TERMS = r"\bhpe\b|hewlett|greenlake|private cloud ai|juniper|nvidia|cray|alletra|opsramp|aruba|mist ai|ai factory"
OUR_TERMS = r"\bour\b|\bwe\b|\binitiatives?\b|\bprojects?\b|\bportfolio\b|mapped|mapping|\bus\b"

# (intent, agent key, method, pattern). Order matters: first match wins.
ROUTES = [
    ("briefing", "reporting", "briefing", r"brief|board|executive summary|prepare .*(summary|pack|report)"),
    ("sensitivity", "scenario", "sensitivity", r"sensitiv|greatest impact|most impact|which variables|tornado"),
    ("scenario", "scenario", "run", r"what (happens|would happen|if)|what-if|\bscenario\b|simulat|\bif (we|infrastructure|utili[sz]ation|cloud|adoption|the)\b"),
    ("roi_movement", "finance", "roi_movement", r"roi.*(fall|fell|decline|drop|down|move|change|lower|worse)|(biggest|largest) roi|roi movement|why.*roi"),
    ("pnl_share", "finance", "pnl_share", r"p ?& ?l|profit and loss|income statement|reflected in (the )?(financ|p|actual)"),
    ("assumption_heavy", "benefits", "assumption_heavy", r"assumption"),
    ("explain_expected", "benefits", "explain_expected", r"explain.*(expected|\$?4\d(\.\d)?m)|expected (ai )?(value|benefit).*(made up|composed|break|explain|built)"),
    ("value_gap", "benefits", "value_gap", r"why.*(below|gap|short|less|lower|behind)|leakage|unrealised|shortfall|\bgap\b"),
    ("budget_variance", "finance", "budget_variance", r"budget variance|over budget|overspend|over-spend|\bvariance"),
    ("cost_growth", "finance", "cost_growth", r"cost growth|driv.*cost|costs? (are |is )?(rising|increas|grow|up)|why.*(cost|spend).*(up|grow|increas|ris)"),
    ("below_plan", "benefits", "below_plan", r"below plan|under ?perform|behind plan|not delivering|benefits? below"),
    ("at_risk", "portfolio", "at_risk", r"at[- ]risk|red flag|watch ?list|which .*risk"),
    ("confidence", "benefits", "confidence", r"confiden|how sure|can we (prove|trust)|how reliable"),
    ("unit_economics", "finance", "unit_economics", r"per (employee|user|transaction|interaction|customer|\$|dollar)|unit economics|cost per|value per"),
    ("bu_spend", "finance", "bu_spend", r"business units?|\bbus?\b|division|which (bu|unit)"),
    ("spend_breakdown", "finance", "spend_breakdown", r"where.*(money|spend|going|spent)|breakdown|split of (spend|cost)|spend by|money going"),
    ("realised_value", "benefits", "realised_value", r"realis|actually (got|achieved|delivered|received)|value .*(delivered|achieved)"),
    ("investment_total", "finance", "investment_total", r"how much.*(invest|spend|spent|spending)|total (ai )?(investment|spend)|investing"),
    ("overview", "reporting", "overview", r"getting value|worth it|value from ai|overall|how are we doing|are we .*value"),
    ("data_query", "portfolio", "data_query", r"^(show|list|find|give me|display|which|what are)|initiatives? (with|above|over|below|in|under|where)|\btop \d|\bprojects? (with|above|over)"),
]

MAX_QUESTION = 500


@lru_cache(maxsize=16)
def context_for(scope: str | None) -> Context:
    return Context(scope)


def clear_contexts() -> None:
    context_for.cache_clear()


def classify(question: str, ctx: Context) -> tuple[str, str, str, dict]:
    ql = question.lower()
    m = re.search(r"\bAI-\d{3}\b", question, re.I)
    names = {n.lower(): i for i, n in zip(ctx.table.initiative_id, ctx.table["name"])}
    mentioned = m.group(0).upper() if m else next((i for n, i in names.items() if n in ql or n.replace("ai ", "") in ql), None)
    if re.search(HPE_TERMS, ql):
        if re.search(r"mapp|categor", ql) and re.search(OUR_TERMS, ql):
            return "hpe_mapping", "research", "portfolio_mapping", {}
        if not re.search(OUR_TERMS, ql):
            return "hpe_research", "research", "answer", {}
    for intent, agent, method, pat in ROUTES:
        if re.search(pat, ql):
            if mentioned and intent in ("data_query", "realised_value", "investment_total", "confidence"):
                return "initiative_detail", "portfolio", "initiative_detail", {"initiative_id": mentioned}
            return intent, agent, method, {}
    if mentioned:
        return "initiative_detail", "portfolio", "initiative_detail", {"initiative_id": mentioned}
    return "fallback", "", "", {}


AGENTS = {"finance": FinanceAnalystAgent, "portfolio": PortfolioAnalystAgent, "benefits": BenefitsAgent,
          "scenario": ScenarioAgent, "research": ResearchAgent, "reporting": ReportingAgent}

SUGGESTIONS = ["How much have we invested in AI?", "How much value has actually been realised?",
               "Why is realised value below expected value?", "What is driving AI cost growth?",
               "Show initiatives with significant budget variance.", "Which benefits rely heavily on assumptions?",
               "Explain the biggest ROI movement.", "What happens if utilisation increases to 80%?",
               "Which business units have the highest AI spend?", "Prepare a board-level AI investment briefing."]


def ask(question: str, principal: Principal | None = None, use_llm: bool = True) -> dict:
    principal = principal or Principal("local", "CFO")
    question = (question or "").strip()
    if not question or len(question) > MAX_QUESTION:
        resp = CopilotResponse(question=question[:MAX_QUESTION], intent="invalid", agent="Orchestrator",
                               answer=f"Please ask a question between 1 and {MAX_QUESTION} characters.",
                               confidence={"level": "High", "basis": "Input validation"})
        return resp.to_dict()
    ctx = context_for(principal.scope)
    intent, agent_key, method, kw = classify(question, ctx)
    try:
        if FORBIDDEN.search(question):
            raise QueryRefused("Only read-only analytical questions are supported; SQL and data-changing requests are not accepted.")
        if not agent_key:
            resp = CopilotResponse(question=question, intent="fallback", agent="Orchestrator",
                                   answer="I can answer questions about AI investment, value, ROI, costs, benefits, risks, scenarios and HPE's public AI portfolio. "
                                          "Try one of the suggested questions.",
                                   confidence={"level": "High", "basis": "No matching analysis; nothing was guessed."}, follow_ups=SUGGESTIONS[:5])
        else:
            resp = getattr(AGENTS[agent_key](ctx), method)(question, **kw)
    except QueryRefused as e:
        resp = CopilotResponse(question=question, intent="refused", agent="Portfolio Analyst Agent", answer=str(e),
                               confidence={"level": "High", "basis": "Query safety controls: only whitelisted read-only queries are executed."})
    llm_meta = {"provider": "offline", "used": False}
    if use_llm and resp.intent not in ("refused", "fallback", "invalid", "hpe_research"):
        pack = "\n".join(f"{n.label}: {n.display}" for n in resp.numbers) + "\n" + "\n".join(resp.key_drivers)
        new, llm_meta = llm.rewrite(resp.answer, pack)
        if llm_meta.get("used"):
            resp.answer, resp.narrative_source = new, f"llm:{llm_meta['provider']} (grounding validated)"
    body = resp.to_dict()
    body.pop("audit_id", None)
    resp.audit_id = audit.record(principal.user_id, principal.role, "copilot.query", {
        "question": question, "intent": resp.intent, "agent": resp.agent, "scope": principal.scope,
        "evidence": [e.ref for e in resp.evidence], "numbers": [n.evidence_id for n in resp.numbers if n.evidence_id],
        "sql": resp.query["sql"] if resp.query else None, "llm": llm_meta}, body)
    out = resp.to_dict()
    out["result_sha256"] = audit.content_hash(body)
    return out
