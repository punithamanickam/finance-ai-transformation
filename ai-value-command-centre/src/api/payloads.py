"""Page payloads shared by the REST API and the static snapshot export, so both show identical numbers."""
from __future__ import annotations

from src import settings
from src.api.serialize import jsonable
from src.finance.confidence import DISCLAIMER, WEIGHTS
from src.finance.formulas import FORMULAS
from src.finance.portfolio import BENEFIT_TYPES, RISK_RULES, records
from src.public import hpe
from src.scenario.engine import LEVERS

INITIATIVE_COLUMNS = [
    "initiative_id", "name", "business_unit", "bu_id", "geography", "hpe_category", "hpe_product_ids", "use_case", "status", "rag",
    "start_date", "planned_go_live", "actual_go_live", "target_completion", "investment", "budget", "actual_spend", "forecast_spend",
    "budget_variance", "budget_variance_pct", "forecast_variance_pct", "users_target", "active_users", "adoption_rate", "adoption_target",
    "cluster_id", "cloud_consumption", "infrastructure_cost", "expected_revenue", "expected_cost_savings", "expected_productivity",
    "expected_risk", "expected_value", "realised_value", "validated_value", "hypothetical_value", "realised_roi", "expected_roi",
    "benefit_realisation", "payback_months", "npv_3yr", "irr_3yr", "confidence", "confidence_band", "open_risks", "risk_exposure",
    "schedule_slip_months", "risk_flags", "owner",
]


def dashboard(ctx) -> dict:
    p = ctx.portfolio
    t = ctx.table
    return jsonable({
        "kpis": ctx.kpis, "quarterly": p.quarterly(), "monthly": p.monthly(), "waterfall": p.waterfall(),
        "classification": {"realised": ctx.kpis["realised_value"], "validated": ctx.kpis["validated_value"],
                           "hypothetical": ctx.kpis["hypothetical_value"], "expected": ctx.kpis["expected_value"],
                           "confidence_by_type": ctx.benefits.by_type()},
        "matrix": t[["initiative_id", "name", "investment", "benefit_realisation", "expected_value", "realised_value", "confidence", "rag", "business_unit"]],
        "roi_movement": {k: v for k, v in p.roi_movement().items() if k not in ("initiatives",)} | {"initiatives": p.roi_movement()["initiatives"][:5]},
        "labels": {"synthetic": settings.SYNTHETIC_LABEL, "public": settings.PUBLIC_LABEL},
        "company": ctx.repo["companies"].drop(columns=["data_label"], errors="ignore").to_dict("records")[0] if len(ctx.repo["companies"]) else {},
        "scope": ctx.bu_scope,
    })


def portfolio(ctx) -> dict:
    t = ctx.table
    cols = [c for c in INITIATIVE_COLUMNS if c in t.columns]
    by_cat = t.groupby("hpe_category").agg(initiatives=("initiative_id", "count"), investment=("investment", "sum"),
                                           realised_value=("realised_value", "sum"), expected_value=("expected_value", "sum")).reset_index()
    return jsonable({"initiatives": records(t[cols]), "by_hpe_category": by_cat, "products": _products(ctx), "rules": RISK_RULES})


def initiative(ctx, initiative_id: str) -> dict | None:
    d = ctx.portfolio.initiative_detail(initiative_id)
    return jsonable(d) if d else None


def investment(ctx) -> dict:
    pc = ctx.repo.programme_costs
    t = ctx.table
    return jsonable({
        "total": ctx.kpis["total_investment"], "budget": ctx.kpis["budget"],
        "by_cost_group": pc.groupby("cost_group").amount.sum().sort_values(ascending=False).to_dict(),
        "by_business_unit": ctx.costs.by_business_unit(),
        "by_hpe_category": t.groupby("hpe_category").investment.sum().sort_values(ascending=False).to_dict(),
        "funding": records(ctx.repo["investment_transactions"].drop(columns=["data_label"], errors="ignore")),
    })


def costs(ctx) -> dict:
    return jsonable({"by_category": ctx.costs.by_category(), "growth": ctx.costs.cost_growth_drivers(),
                     "unit_economics": ctx.costs.unit_economics(), "infrastructure": ctx.costs.infrastructure(),
                     "vendors": ctx.costs.by_vendor(), "monthly": ctx.portfolio.monthly()})


def benefits(ctx) -> dict:
    return jsonable({"lines": ctx.benefits.realisation_table(), "leakage": ctx.benefits.leakage_summary(),
                     "pnl": ctx.benefits.pnl_reflection(), "assumption_dependency": ctx.benefits.assumption_dependency(),
                     "confidence_by_type": ctx.benefits.by_type(), "confidence_weights": WEIGHTS, "confidence_disclaimer": DISCLAIMER,
                     "types": BENEFIT_TYPES})


def roi(ctx) -> dict:
    t = ctx.table
    return jsonable({"kpis": {k: ctx.kpis[k] for k in ("realised_roi", "expected_roi", "value_per_dollar", "net_value", "expected_net_value", "npv_3yr")},
                     "quarterly": ctx.portfolio.quarterly(), "movement": ctx.portfolio.roi_movement(),
                     "lifecycle": t[["initiative_id", "name", "npv_3yr", "irr_3yr", "payback_months", "outlook_annual_net"]],
                     "formulas": FORMULAS})


def risks(ctx) -> dict:
    r = ctx.repo["risks"].copy()
    names = ctx.table.set_index("initiative_id")["name"]
    r["initiative_name"] = r.initiative_id.map(names)
    r["exposure"] = r.financial_impact * r.probability
    heat = r[r.status != "Closed"].groupby("category").agg(risks=("risk_id", "count"), exposure=("exposure", "sum"),
                                                            impact=("financial_impact", "sum")).reset_index().sort_values("exposure", ascending=False)
    return jsonable({"risks": records(r.drop(columns=["data_label"], errors="ignore").sort_values("exposure", ascending=False)), "by_category": heat,
                     "note": "Probabilities are owner assessments recorded at the FY26 Q4 risk review, not model predictions."})


def scenario_meta(ctx) -> dict:
    eng = ctx.scenario
    return jsonable({"levers": {k: {"label": v[0], "default": (v[1] if v[1] is not None else eng.base["utilisation"]), "min": v[2], "max": v[3],
                                    "step": v[4], "unit": v[5]} for k, v in LEVERS.items()},
                     "base": eng.base, "assumptions": eng.assumptions, "baseline": eng.run({}), "sensitivity": eng.sensitivity(),
                     "utilisation_80": eng.run({"utilisation_target": 0.80}), "invest_10m": eng.run({"additional_investment": 10_000_000})})


def assumptions(ctx) -> list[dict]:
    return jsonable(records(ctx.repo["assumptions"].drop(columns=["data_label"], errors="ignore")))


def _products(ctx) -> list[dict]:
    p = ctx.repo["hpe_products"]
    s = ctx.repo["hpe_sources"].set_index("source_id") if len(ctx.repo["hpe_sources"]) else None
    out = []
    for r in p.to_dict("records"):
        src = s.loc[r["source_id"]] if s is not None and r["source_id"] in s.index else None
        out.append({**r, "url": src.url if src is not None else None, "source_title": src.title if src is not None else None,
                    "date": src.date if src is not None else None})
    return out


def sources(ctx) -> dict:
    return jsonable({"sources": hpe.source_rows(), "products": _products(ctx), "headline": hpe.headline(),
                     "label": settings.PUBLIC_LABEL})


def evidence(ctx, evidence_id: str) -> dict | None:
    e = ctx.portfolio.get_evidence(evidence_id)
    if e is None:
        return None
    ids = [a for a in e.get("assumptions", [])]
    e["assumption_details"] = ctx.assumptions(ids)
    return jsonable(e)
