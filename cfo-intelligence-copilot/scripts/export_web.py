"""Export the engine's outputs to a self-contained HTML/JS console (web/cfo-copilot-console.html).

    python -m scripts.export_web

The page needs no server: every number, answer and citation is produced here by the Python engine and embedded as
JSON. The scenario lab re-runs the documented scenario formulas in JavaScript from the same base inputs.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import pandas as pd

from app.chat.views import DEMO_QUESTIONS, KILLER_DEMO, MORE
from src import settings
from src.calculations.driver_trees import free_cash_flow_tree, operating_income_tree, revenue_tree
from src.calculations.engine import CalculationEngine
from src.calculations.models import format_value
from src.calculations.scenario import DISCLAIMER, ScenarioEngine
from src.calculations.variance import MAJOR_METRICS, explain_variance
from src.copilot.copilot import CFOCopilot
from src.copilot.llm import OfflineProvider
from src.governance.audit import read_audit_log
from src.governance.data_quality import run_checks
from src.governance.prompts import load_prompt
from src.ingestion.source_registry import load_registry
from src.reporting.brief import build_brief

WEB = settings.PROJECT_ROOT / "web"
TEMPLATE = WEB / "template.html"
OUT = WEB / "cfo-copilot-console.html"


def clean(o):
    if isinstance(o, float):
        return None if math.isnan(o) or math.isinf(o) else round(o, 6)
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    return o


def tree_json(node) -> dict:
    return {"id": node.node_id, "label": node.label, "current": node.current, "prior": node.prior, "change": node.change,
            "share": node.share_of_parent_change, "formula": node.formula, "note": node.note,
            "children": [tree_json(c) for c in node.children]}


def response_json(r, group: str) -> dict:
    ev = r.evidence
    keep_tables = {k: v for k, v in ev.tables.items() if k in {
        "operating_margin_decomposition", "segments", "expense_movements_ranked_by_absolute_change", "attention_flags",
        "scenario_results", "assumptions", "sensitivity_operating_income", "segment_gross_margin", "offering_growth"}}
    return {
        "question": r.question, "group": group, "intent": r.intent, "title": r.title, "answer": r.answer, "status": r.status,
        "confidence": ev.confidence, "basis": ev.basis, "disclaimer": ev.disclaimer,
        "key_numbers": [k.model_dump(include={"metric", "current", "prior", "change", "current_label", "prior_label"}) for k in ev.key_numbers],
        "statements": [s.model_dump() for s in ev.statements],
        "sources": [s.model_dump() for s in ev.sources],
        "calculations": [{"name": c.name, "fy": c.fiscal_year, "value": c.display(2), "formula": c.formula, "inputs": c.formula_with_values,
                          "status": c.status, "proxy": c.is_proxy, "engine": c.engine_version} for c in ev.calculations],
        "tables": keep_tables, "audit_id": r.audit_id, "validation": r.validation.get("notes", ""),
    }


def main() -> str:
    eng = CalculationEngine()
    fy = eng.repo.latest_year
    brief = build_brief(eng, fy)

    cp = CFOCopilot(provider=OfflineProvider(), engine=eng, session_id="web-export")
    responses = []
    for group, qs in [("Executive demo", DEMO_QUESTIONS), ("Killer demo", KILLER_DEMO), ("More", MORE),
                      ("More", ["How did revenue change year over year?", "Is operating leverage improving?", "Which segment is growing fastest?",
                                "How much capital expenditure is being invested?", "What percentage of operating cash flow is being reinvested?",
                                "Are operating expenses growing faster or slower than revenue?", "How has R&D as a percentage of revenue changed?",
                                "What is the trend in net income?", "What is revenue per employee?", "What is the weakest-performing segment based on the available financial metrics?"])]:
        for q in qs:
            responses.append(response_json(cp.ask(q), group))

    variance = []
    for mid in MAJOR_METRICS:
        ex = explain_variance(eng, mid, fy, fy - 1)
        v = ex.variance
        variance.append({"id": mid, "label": v.label, "unit": v.unit, "current": v.current, "prior": v.prior,
                         "current_fmt": format_value(v.current, v.unit), "prior_fmt": format_value(v.prior, v.unit),
                         "abs": v.absolute_change, "abs_fmt": (format_value(v.absolute_change, "pp") if v.unit == "%" else format_value(v.absolute_change, v.unit)) if v.absolute_change is not None else "n/a",
                         "pct": v.pct_change, "direction": v.direction, "favourable": v.favourable, "status": v.status,
                         "evidence": [{"text": e["text"][:900], "citation": e["citation"], "url": e["url"]} for e in ex.evidence],
                         "explanation": ex.explanation,
                         "inputs": [{"label": i.label, "fy": i.fiscal_year, "value": i.value, "page": i.page, "document": i.document} for i in v.inputs]})

    se = ScenarioEngine(eng)
    base_a, src = se.base_assumptions()
    scenario = {"base_year": fy, "revenue": eng.value("revenue", fy), "rd": eng.value("research_and_development", fy),
                "sm": eng.value("sales_and_marketing", fy), "ga": eng.value("general_and_administrative", fy),
                "assumptions": base_a.model_dump(), "sources": src, "disclaimer": DISCLAIMER,
                "check": se.compare(deltas={"revenue_growth": -0.05}).delta}

    repo = eng.repo
    facts = repo.df[["fact_key", "reporting_period", "statement", "metric_label", "dimension_label", "value", "unit", "source_document",
                     "source_page", "source_section", "source_table", "row_label", "column_label", "xbrl_concept", "extraction_method",
                     "consistency", "restated_vs_prior_filing", "source_url"]].to_dict("records")
    statements = {}
    for stmt in ["Income Statement", "Balance Sheet", "Cash Flow Statement"]:
        piv = repo.statement(stmt)
        statements[stmt] = {"years": [int(c) for c in piv.columns],
                            "rows": [{"label": lbl, "values": [None if pd.isna(x) else float(x) for x in row]} for (mid, lbl), row in piv.iterrows()]}
    checks = run_checks(repo)
    conflicts = pd.read_csv(settings.CONFLICTS_CSV).to_dict("records") if settings.CONFLICTS_CSV.exists() else []
    reg = load_registry()
    prompt = load_prompt("cfo_copilot_system")
    audit = [r for r in read_audit_log(400) if r.get("session_id") == "web-export"][:30]

    data = clean({
        "meta": {"company": settings.COMPANY, "fy": fy, "prior": fy - 1, "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                 "engine": settings.CALC_ENGINE_VERSION, "prompt_ref": prompt.ref, "facts": len(repo.df),
                 "dq_passed": sum(c.passed for c in checks), "dq_total": len(checks), "years": repo.years("revenue")},
        "kpis": [k.__dict__ for k in brief.kpis],
        "trends": brief.trends,
        "glance": brief.at_a_glance,
        "responses": responses,
        "variance": variance,
        "trees": {"operating_income": tree_json(operating_income_tree(eng, fy)), "revenue": tree_json(revenue_tree(eng, fy)),
                  "free_cash_flow": tree_json(free_cash_flow_tree(eng, fy))},
        "segments": [{k: v for k, v in r.items() if k != "inputs"} for r in eng.segment_table(fy)],
        "scenario": scenario,
        "statements": statements,
        "facts": facts,
        "checks": [{"category": c.category, "name": c.name, "fy": c.fiscal_year, "expected": c.expected, "actual": c.actual, "passed": c.passed}
                   for c in checks],
        "conflicts": conflicts,
        "sources": reg[["source_id", "short_name", "source_type", "reporting_period", "filing_date", "retrieval_date", "source_url", "role"]].to_dict("records"),
        "prompt": prompt.text,
        "audit": [{"id": r["interaction_id"], "timestamp": r["timestamp"], "question": r["user_query"], "intent": r.get("intent"),
                   "confidence": r.get("confidence"), "answer_source": r.get("answer_source"), "sha": r.get("final_answer_sha256"),
                   "steps": [{k: v for k, v in s.items() if k not in {"chunks"}} | ({"chunks": s["chunks"][:4]} if "chunks" in s else {})
                             for s in r["steps"]]} for r in audit],
    })
    payload = json.dumps(data, separators=(",", ":"), default=str).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__CFO_DATA__*/null", payload)
    OUT.write_text(html, encoding="utf-8")
    return f"{OUT} ({len(html) / 1024:,.0f} KB, {len(responses)} answers)"


if __name__ == "__main__":
    print(main())
