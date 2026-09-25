"""CFO Copilot orchestrator.

    question -> intent detection -> metric identification -> structured data -> Python calculation
             -> validation -> LLM explanation (optional) -> numeric grounding check -> source citation -> audit log
"""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from src import settings
from src.calculations.engine import CalculationEngine
from src.copilot import handlers as H
from src.copilot.evidence import BASIS_LABELS, Evidence
from src.copilot.intent import detect_intent
from src.copilot.llm import LLMProvider, get_provider
from src.copilot.validation import validate_numbers
from src.governance.audit import AuditTrail
from src.governance.prompts import load_prompt


class CopilotResponse(BaseModel):
    question: str
    intent: str
    title: str
    status: str
    answer: str
    answer_source: str  # llm | deterministic
    evidence: Evidence
    validation: dict = Field(default_factory=dict)
    model: str = ""
    provider: str = ""
    prompt_ref: str = ""
    audit_id: str = ""

    @property
    def confidence(self) -> str:
        return self.evidence.confidence

    def drivers_by_basis(self) -> dict[str, list]:
        out: dict[str, list] = {k: [] for k in BASIS_LABELS}
        for s in self.evidence.statements:
            out[s.basis].append(s)
        return out

    def to_markdown(self) -> str:
        ev = self.evidence
        lines = [f"### {self.title}", "", "**ANSWER**", "", self.answer, ""]
        if ev.disclaimer:
            lines += [f"> ⚠️ {ev.disclaimer}", ""]
        if ev.key_numbers:
            lines += ["**KEY NUMBERS**", "", "| Metric | Current | Prior | Change |", "|---|---:|---:|---:|"]
            for k in ev.key_numbers:
                lines.append(f"| {k.metric} | {k.current} ({k.current_label}) | {k.prior} ({k.prior_label}) | {k.change} |")
            lines.append("")
        lines += ["**DRIVERS**", ""]
        for basis, items in self.drivers_by_basis().items():
            if items:
                lines.append(f"*{BASIS_LABELS[basis]}*")
                for s in items:
                    cite = f" — _{'; '.join(s.citations)}_" if s.citations else ""
                    lines.append(f"- {s.text}{cite}")
                lines.append("")
        lines += ["**SOURCE**", ""]
        for s in ev.sources[:12]:
            lines.append(f"- Document: {s.document} | Section: {s.section} | Page: {s.page} | {s.detail} | [link]({s.url})")
        if len(ev.sources) > 12:
            lines.append(f"- … {len(ev.sources) - 12} more source locations in the audit log")
        lines += ["", f"**CONFIDENCE:** {ev.confidence}", "", f"**BASIS:** {' / '.join(ev.basis) or 'n/a'}", ""]
        return "\n".join(lines)


def _confidence_rules(ev: Evidence) -> None:
    if ev.status in {"insufficient_evidence", "conflict"}:
        ev.confidence = "Low"
    if any(c.status != "ok" for c in ev.calculations):
        ev.lower_confidence("Medium")


class CFOCopilot:
    def __init__(self, provider: LLMProvider | None = None, engine: CalculationEngine | None = None, session_id: str = "local"):
        self.engine = engine or CalculationEngine()
        self.provider = provider or get_provider()
        self.prompt = load_prompt("cfo_copilot_system")
        self.session_id = session_id
        self.history: list[CopilotResponse] = []

    @property
    def last_evidence(self) -> Evidence | None:
        for r in reversed(self.history):
            if r.intent not in {"show_source", "show_calculation"}:
                return r.evidence
        return None

    def _build_evidence(self, question: str, audit: AuditTrail) -> Evidence:
        it = detect_intent(question, self.engine.repo.latest_year)
        audit.step("intent_detection", intent=it.name, sub=it.sub, rule=it.matched_rule, fiscal_year=it.fiscal_year, prior_year=it.prior_year,
                   metrics_selected=it.metrics, scenario=it.scenario)
        e = self.engine
        dispatch = {
            "metric_change": lambda: H.metric_change(e, it),
            "biggest_changes": lambda: H.biggest_changes(e, it),
            "brief": lambda: H.biggest_changes(e, it),
            "oi_drivers": lambda: H.oi_drivers(e, it),
            "margin_drivers": lambda: H.margin_drivers(e, it),
            "expenses": lambda: H.expenses(e, it),
            "segment": lambda: H.segment(e, it, question),
            "cash_position": lambda: H.cash_position(e, it),
            "cash_flow": lambda: H.cash_flow(e, it),
            "investment": lambda: H.investment(e, it, question),
            "comparison": lambda: H.comparison(e, it),
            "profitability_bridge": lambda: H.profitability_bridge(e, it),
            "operating_leverage": lambda: H.operating_leverage(e, it),
            "risks": lambda: H.risks(e, it),
            "opportunities": lambda: H.opportunities(e, it),
            "cfo_attention": lambda: H.cfo_attention(e, it),
            "scenario": lambda: H.scenario(e, it),
            "sensitivity": lambda: H.sensitivity(e, it),
            "forecast_request": lambda: H.forecast_request(e, it),
            "show_source": lambda: H.show_evidence(self.last_evidence, calculation=False),
            "show_calculation": lambda: H.show_evidence(self.last_evidence, calculation=True),
            "document_qa": lambda: H.document_qa(e, it, question),
        }
        ev = dispatch.get(it.name, dispatch["document_qa"])()
        _confidence_rules(ev)
        return ev

    def ask(self, question: str) -> CopilotResponse:
        audit = AuditTrail(question, self.session_id)
        ev = self._build_evidence(question, audit)
        audit.step("retrieved_sources", chunks=ev.retrieved_chunks, n_structured_sources=len(ev.sources))
        audit.step("calculations", calculations=[{"metric": c.metric_id, "fy": c.fiscal_year, "value": c.value, "formula": c.formula,
                                                  "inputs": [i.fact_key for i in c.inputs], "status": c.status, "engine": c.engine_version}
                                                 for c in ev.calculations])
        answer, source, validation = ev.headline, "deterministic", {"passed": True, "checked": 0, "unsupported": [], "notes": "deterministic narrative"}
        model = self.provider.model
        if ev.status in {"ok"} and ev.intent not in {"show_source", "show_calculation"} and self.provider.name != "offline":
            pack = ev.pack()
            user = (f"CFO question: {question}\n\nEVIDENCE PACK (JSON):\n{json.dumps(pack, default=str)}\n\n"
                    "Write the ANSWER section now.")
            audit.step("llm_prompt", provider=self.provider.name, model=self.provider.model, prompt_ref=self.prompt.ref, user_prompt_chars=len(user))
            res = self.provider.generate(self.prompt.text, user)
            model = res.model
            audit.step("llm_response", ok=res.ok, text=res.text, error=res.error, usage=res.usage, stop_reason=res.stop_reason)
            if res.ok and res.text:
                v = validate_numbers(res.text, pack)
                validation = v.__dict__
                if v.passed:
                    answer, source = res.text, "llm"
                else:
                    validation["notes"] = f"LLM narrative rejected - unsupported numbers {v.unsupported}; deterministic narrative used"
            else:
                validation["notes"] = f"LLM unavailable ({res.error}); deterministic narrative used"
        audit.step("validation", **validation)
        resp = CopilotResponse(question=question, intent=ev.intent, title=ev.title, status=ev.status, answer=answer, answer_source=source,
                               evidence=ev, validation=validation, model=model, provider=self.provider.name, prompt_ref=self.prompt.ref)
        audit.set(model=model, provider=self.provider.name, prompt_version=self.prompt.ref, calculation_engine=f"v{settings.CALC_ENGINE_VERSION}",
                  retrieval="TF-IDF cosine over filing chunks", confidence=ev.confidence, basis=ev.basis, intent=ev.intent,
                  answer_source=source, status=ev.status)
        rec = audit.finalize({"answer": answer, "key_numbers": [k.model_dump() for k in ev.key_numbers],
                              "sources": [s.model_dump() for s in ev.sources]})
        resp.audit_id = rec["interaction_id"]
        self.history.append(resp)
        return resp
