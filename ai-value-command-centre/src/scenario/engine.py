"""Scenario simulator and sensitivity analysis.

The engine is a pure function `run(base, levers, assumptions)` over a small, documented base snapshot, so the same
maths can run in the browser (web/scenario.js) and is checked against this implementation in tests.

All scenario outputs are ILLUSTRATIVE: they apply documented assumptions to the synthetic FY2026 base. They are not
forecasts.

Lever formulas (12-month horizon, same basis as the FY2026 base)
  additional_investment   dV = dI x top-performer expected value per $ x A-35
  utilisation_target      dGPUh = annual capacity x (u1 - u0) of new workloads on existing capacity
                          dV = dGPUh x value per used GPU-hour x A-33
                          dC = dGPUh x (non-infrastructure investment per used GPU-hour x A-36 + A-34)
                          infrastructure avoided = dGPUh x infrastructure cost per capacity GPU-hour (reported, not netted)
  cloud_cost_change       dC = cloud spend x change
  productivity_change     dV = productivity expected value x change
  revenue_uplift_change   dV = revenue expected value x change
  adoption_change         dV = productivity expected value x change (user-driven benefits scale with active users)
  benefit_realisation     dV = (expected benefit + all benefit deltas above) x (rate - 1)
  project_delay_months    dV = - in-flight expected value x months x A-37
  implementation_cost_change  dC = investment x change
"""
from __future__ import annotations

from copy import deepcopy

from src.finance import formulas as F

LEVERS = {
    # name: (label, default, min, max, step, unit)
    "additional_investment": ("Additional AI investment", 0.0, 0.0, 25_000_000.0, 500_000.0, "USD"),
    "utilisation_target": ("Infrastructure utilisation", None, 0.40, 0.95, 0.01, "share"),
    "cloud_cost_change": ("Cloud cost change", 0.0, -0.5, 0.5, 0.05, "share"),
    "productivity_change": ("Employee productivity change", 0.0, -0.5, 0.5, 0.05, "share"),
    "revenue_uplift_change": ("Revenue uplift change", 0.0, -0.5, 0.5, 0.05, "share"),
    "adoption_change": ("AI adoption change", 0.0, -0.5, 0.5, 0.05, "share"),
    "benefit_realisation": ("Benefit realisation rate", 1.0, 0.3, 1.3, 0.05, "share"),
    "project_delay_months": ("Project delay", 0.0, 0.0, 12.0, 1.0, "months"),
    "implementation_cost_change": ("Implementation cost change", 0.0, -0.3, 0.5, 0.05, "share"),
}
SCENARIO_ASSUMPTIONS = ("A-33", "A-34", "A-35", "A-36", "A-37")


def build_base(portfolio) -> dict:
    """Snapshot of the FY2026 figures the scenario maths needs (all derived from the database)."""
    t = portfolio.initiative_table()
    r = portfolio.repo
    iu = r["infrastructure_usage"]
    q4 = iu[iu.quarter == "FY26-Q4"]
    bm, ox = r["benefit_monthly"], r.incremental_opex
    measured_q4 = bm[bm.quarter == "FY26-Q4"].measured_value.sum()
    pc = r.programme_costs
    top = t[t.rag == "Green"]
    in_flight = t[t.actual_go_live >= "2026-01-01"]
    base = {
        "investment": float(t.investment.sum()),
        "expected_value": float(t.expected_value.sum()),
        "expected_benefit": float(t.business_case_benefit.sum()),
        "incremental_opex": float(t.incremental_opex_plan.sum()),
        "expected_productivity": float(t.expected_productivity.sum()),
        "expected_revenue": float(t.expected_revenue.sum()),
        "cloud_spend": float(pc[pc.cost_group == "Cloud"].amount.sum()),
        "utilisation": float(q4.gpu_hours_used.sum() / q4.gpu_hours_capacity.sum()),
        "capacity_gpu_hours_annual": float(q4.gpu_hours_capacity.sum() * 4),
        "used_gpu_hours_annual": float(q4.gpu_hours_used.sum() * 4),
        "measured_value_annual_run_rate": float((measured_q4 - ox[ox.quarter == "FY26-Q4"].amount.sum()) * 4),
        "top_performer_value_per_dollar": float(top.expected_value.sum() / top.investment.sum()) if len(top) else 1.0,
        "in_flight_expected_value": float(in_flight.expected_value.sum()),
        "in_flight_initiatives": list(in_flight.initiative_id),
    }
    base["value_per_used_gpu_hour"] = base["measured_value_annual_run_rate"] / base["used_gpu_hours_annual"]
    infra = float(pc[pc.cost_group.isin(["Infrastructure", "Cloud"])].amount.sum())
    # run-rate basis (FY26-Q4 annualised), consistent with value per used GPU-hour
    base["non_infra_investment_per_used_gpu_hour"] = (base["investment"] - infra) / base["used_gpu_hours_annual"]
    base["infra_cost_per_capacity_gpu_hour"] = float(iu.infrastructure_cost.sum() / iu.gpu_hours_capacity.sum())
    return base


def assumption_values(repo) -> dict:
    return {a: repo.assumption(a) for a in SCENARIO_ASSUMPTIONS}


def run(base: dict, levers: dict, assumptions: dict) -> dict:
    lv = {k: (v[1] if v[1] is not None else base["utilisation"]) for k, v in LEVERS.items()}
    lv.update({k: float(v) for k, v in (levers or {}).items() if k in LEVERS and v is not None})
    A = assumptions
    bridge = []

    def add(lever, label, dv=0.0, dc=0.0, note=""):
        if abs(dv) > 0.005 or abs(dc) > 0.005:
            bridge.append({"lever": lever, "label": label, "value_change": dv, "cost_change": dc, "note": note})

    add("additional_investment", "Additional investment in proven use cases",
        lv["additional_investment"] * base["top_performer_value_per_dollar"] * A["A-35"], lv["additional_investment"],
        f"value per $ of Green initiatives {base['top_performer_value_per_dollar']:.2f} x A-35 {A['A-35']:.2f}")
    d_util = lv["utilisation_target"] - base["utilisation"]
    d_hours = base["capacity_gpu_hours_annual"] * d_util
    if abs(d_util) > 1e-9:
        dc = d_hours * (base["non_infra_investment_per_used_gpu_hour"] * A["A-36"] + A["A-34"])
        add("utilisation_target", "Infrastructure utilisation (new workloads on existing capacity)",
            d_hours * base["value_per_used_gpu_hour"] * A["A-33"], dc,
            f"{d_hours:,.0f} GPU-hours x ${base['value_per_used_gpu_hour']:.2f} value x A-33 {A['A-33']:.2f}; "
            f"onboarding ${base['non_infra_investment_per_used_gpu_hour']:.2f}/GPU-hour + run ${A['A-34']:.2f}/GPU-hour")
    add("cloud_cost_change", "Cloud cost", 0.0, base["cloud_spend"] * lv["cloud_cost_change"])
    add("productivity_change", "Employee productivity", base["expected_productivity"] * lv["productivity_change"])
    add("revenue_uplift_change", "Revenue uplift", base["expected_revenue"] * lv["revenue_uplift_change"])
    add("adoption_change", "AI adoption (productivity benefits)", base["expected_productivity"] * lv["adoption_change"])
    add("implementation_cost_change", "Implementation cost", 0.0, base["investment"] * lv["implementation_cost_change"])
    add("project_delay_months", "Project delay (in-flight initiatives)",
        -base["in_flight_expected_value"] * lv["project_delay_months"] * A["A-37"])
    gross = base["expected_benefit"] + sum(b["value_change"] for b in bridge)
    add("benefit_realisation", "Benefit realisation rate", gross * (lv["benefit_realisation"] - 1.0))

    d_value = sum(b["value_change"] for b in bridge)
    d_cost = sum(b["cost_change"] for b in bridge)
    s_inv = base["investment"] + d_cost
    s_val = base["expected_value"] + d_value
    monthly_incr = d_value / 12
    result = {
        "levers": lv,
        "base": {"investment": base["investment"], "expected_value": base["expected_value"],
                 "net_value": base["expected_value"] - base["investment"], "roi": F.roi(base["expected_value"], base["investment"]),
                 "utilisation": base["utilisation"]},
        "scenario": {"investment": s_inv, "expected_value": s_val, "net_value": s_val - s_inv, "roi": F.roi(s_val, s_inv),
                     "utilisation": lv["utilisation_target"]},
        "incremental": {"cost": d_cost, "value": d_value, "net_value": d_value - d_cost,
                        "roi": F.incremental_roi(d_value, d_cost) if d_cost > 0 else None,
                        "capacity_gpu_hours": d_hours,
                        "infrastructure_avoided": max(d_hours, 0.0) * base["infra_cost_per_capacity_gpu_hour"],
                        "payback_months": (d_cost / monthly_incr) if d_cost > 0 and monthly_incr > 0 else None},
        "bridge": bridge,
        "assumptions": [{"assumption_id": k, "value": v} for k, v in A.items()],
        "label": "ILLUSTRATIVE scenario on SYNTHETIC data - not a forecast",
    }
    return result


def sensitivity(base: dict, assumptions: dict, swing: float = 0.2) -> list[dict]:
    """Tornado: effect on scenario net value of moving each driver by +/- swing (utilisation +/- 10pp)."""
    ref = run(base, {}, assumptions)["scenario"]["net_value"]
    tests = {
        "utilisation_target": ("Infrastructure utilisation (+/-10pp)", base["utilisation"] - 0.10, base["utilisation"] + 0.10),
        "adoption_change": ("AI adoption", -swing, swing),
        "revenue_uplift_change": ("Revenue uplift", -swing, swing),
        "productivity_change": ("Productivity improvement", -swing, swing),
        "cloud_cost_change": ("Cloud cost", swing, -swing),
        "implementation_cost_change": ("Implementation cost", swing, -swing),
        "benefit_realisation": ("Benefit realisation", 1 - swing, 1 + swing),
    }
    out = []
    for lever, (label, lo, hi) in tests.items():
        low = run(base, {lever: lo}, assumptions)["scenario"]["net_value"] - ref
        high = run(base, {lever: hi}, assumptions)["scenario"]["net_value"] - ref
        out.append({"lever": lever, "label": label, "low": low, "high": high, "swing": abs(high - low),
                    "low_input": lo, "high_input": hi})
    return sorted(out, key=lambda x: -x["swing"])


class ScenarioEngine:
    def __init__(self, portfolio):
        self.p = portfolio
        self.base = build_base(portfolio)
        self.assumptions = assumption_values(portfolio.repo)

    def run(self, levers: dict | None = None) -> dict:
        res = run(self.base, levers or {}, self.assumptions)
        a = self.p.repo["assumptions"].set_index("assumption_id")
        res["assumptions"] = [{"assumption_id": k, "value": v, "description": a.loc[k, "description"], "unit": a.loc[k, "unit"],
                               "source": a.loc[k, "source"]} for k, v in self.assumptions.items()]
        res["base_inputs"] = deepcopy(self.base)
        return res

    def sensitivity(self, swing: float = 0.2) -> list[dict]:
        return sensitivity(self.base, self.assumptions, swing)
