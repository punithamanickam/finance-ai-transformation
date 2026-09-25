"""FastAPI service - the same engines the Streamlit UI uses, exposed for integration (BI tools, Teams/Slack bots, ERP portals).

    uvicorn src.api.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.calculations.driver_trees import free_cash_flow_tree, operating_income_tree, revenue_tree
from src.calculations.engine import METRICS, CalculationEngine
from src.calculations.scenario import ScenarioEngine
from src.calculations.variance import variance_table
from src.copilot.copilot import CFOCopilot
from src.governance.audit import read_audit_log
from src.reporting.report import render_report

app = FastAPI(title="CFO Intelligence Copilot API", version="1.0.0",
              description="Independent proof-of-concept over public SEC filings. Deterministic calculations; LLM narrative constrained to evidence.")
_engine = CalculationEngine()
_sessions: dict[str, CFOCopilot] = {}


class AskRequest(BaseModel):
    question: str
    session_id: str = "api"


class ScenarioRequest(BaseModel):
    deltas: dict[str, float] = {}
    overrides: dict[str, float] = {}


@app.get("/health")
def health():
    return {"status": "ok", "latest_fiscal_year": _engine.repo.latest_year, "facts": len(_engine.repo.df)}


@app.get("/facts")
def facts(metric_id: str | None = None, fiscal_year: int | None = None):
    d = _engine.repo.df
    if metric_id:
        d = d[d.metric_id == metric_id]
    if fiscal_year:
        d = d[d.fiscal_year == fiscal_year]
    return d.head(500).to_dict("records")


@app.get("/metrics")
def list_metrics():
    return [{"metric_id": m.metric_id, "name": m.name, "unit": m.unit, "formula": m.formula, "proxy": m.is_proxy, "note": m.note} for m in METRICS.values()]


@app.get("/metrics/{metric_id}/{fiscal_year}")
def metric(metric_id: str, fiscal_year: int):
    r = _engine.calculate(metric_id, fiscal_year)
    if r.status == "unavailable" and r.formula == "reported value":
        raise HTTPException(404, r.note)
    return r.model_dump()


@app.get("/variance/{fiscal_year}")
def variance(fiscal_year: int, prior: int | None = None):
    return [v.model_dump() for v in variance_table(_engine, fiscal_year, prior)]


@app.get("/driver-tree/{tree}/{fiscal_year}")
def driver_tree(tree: str, fiscal_year: int):
    fn = {"revenue": revenue_tree, "operating-income": operating_income_tree, "free-cash-flow": free_cash_flow_tree}.get(tree)
    if not fn:
        raise HTTPException(404, "tree must be revenue | operating-income | free-cash-flow")
    return fn(_engine, fiscal_year).model_dump()


@app.post("/scenario")
def scenario(req: ScenarioRequest):
    return ScenarioEngine(_engine).compare(overrides=req.overrides, deltas=req.deltas).model_dump()


@app.get("/sensitivity")
def sensitivity(target: str = "operating_income"):
    return ScenarioEngine(_engine).sensitivity(target)


@app.post("/ask")
def ask(req: AskRequest):
    cp = _sessions.setdefault(req.session_id, CFOCopilot(engine=_engine, session_id=req.session_id))
    r = cp.ask(req.question)
    return {"answer": r.answer, "answer_source": r.answer_source, "intent": r.intent, "status": r.status, "confidence": r.confidence,
            "basis": r.evidence.basis, "key_numbers": [k.model_dump() for k in r.evidence.key_numbers],
            "drivers": [s.model_dump() for s in r.evidence.statements], "sources": [s.model_dump() for s in r.evidence.sources],
            "calculations": [c.model_dump() for c in r.evidence.calculations], "disclaimer": r.evidence.disclaimer,
            "validation": r.validation, "audit_id": r.audit_id, "markdown": r.to_markdown()}


@app.get("/report", response_class=HTMLResponse)
def report():
    return render_report()


@app.get("/audit")
def audit(limit: int = 50):
    return read_audit_log(limit)
