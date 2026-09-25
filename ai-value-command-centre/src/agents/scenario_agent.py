"""Scenario Agent: turns a what-if question into scenario levers and runs the deterministic scenario engine."""
from __future__ import annotations

import re

from src.agents.base import Agent, Drilldown, Number, ds
from src.copilot.response import money, pct
from src.scenario.engine import LEVERS

_NUM = r"([+-]?\d+(?:\.\d+)?)\s*(%|m\b|mn\b|million|k\b|b\b|bn\b|billion)?"


def _money(v: str, unit: str | None) -> float:
    x = float(v)
    unit = (unit or "").lower()
    return x * (1e6 if unit in ("m", "mn", "million") else 1e3 if unit == "k" else 1e9 if unit in ("b", "bn", "billion") else 1)


def parse_levers(question: str, base_utilisation: float) -> dict:
    ql = question.lower()
    lv: dict[str, float] = {}
    m = re.search(r"utili[sz]ation[^\d%]*(?:from\s*\d+(?:\.\d+)?\s*%?\s*)?(?:to|reach(?:es)?|of|at|=)\s*" + r"(\d+(?:\.\d+)?)\s*%", ql)
    if m:
        lv["utilisation_target"] = float(m.group(1)) / 100
    elif re.search(r"utili[sz]ation", ql):
        m = re.search(r"utili[sz]ation[^\d]*(?:increases?|rises?|improves?|goes up)\s*(?:by)?\s*(\d+(?:\.\d+)?)\s*(?:pp|points|%)", ql)
        if m:
            lv["utilisation_target"] = base_utilisation + float(m.group(1)) / 100
    m = re.search(r"(?:invest|investment|spend)[^\d$]*\$?\s*" + _NUM + r"\s*(?:more|additional|extra)?", ql)
    if m and re.search(r"additional|extra|more|another|increase", ql):
        lv["additional_investment"] = _money(m.group(1), m.group(2))
    for key, pat in [("cloud_cost_change", r"cloud (?:cost|spend|price)s?"), ("productivity_change", r"productivity"),
                     ("revenue_uplift_change", r"revenue(?: uplift)?"), ("adoption_change", r"adoption"),
                     ("implementation_cost_change", r"implementation cost")]:
        m = re.search(pat + r"[^\d]*?(increases?|rises?|grows?|goes up|up|decreases?|falls?|drops?|down|reduces?|improves?)?\s*(?:by)?\s*" + r"(\d+(?:\.\d+)?)\s*%", ql)
        if m:
            sign = -1 if (m.group(1) or "").startswith(("decrease", "fall", "drop", "down", "reduce")) else 1
            lv[key] = sign * float(m.group(2)) / 100
    m = re.search(r"realis(?:ation|ed)(?: rate)?[^\d]*(\d+(?:\.\d+)?)\s*%", ql)
    if m:
        lv["benefit_realisation"] = float(m.group(1)) / 100
    m = re.search(r"(\d+)\s*(?:-|\s)?months?\s*(?:delay|late|slip)|delay(?:ed)?\s*(?:by|of)?\s*(\d+)\s*months?", ql)
    if m:
        lv["project_delay_months"] = float(m.group(1) or m.group(2))
    return {k: v for k, v in lv.items() if k in LEVERS}


class ScenarioAgent(Agent):
    name = "Scenario Agent"

    def run(self, q: str):
        eng = self.ctx.scenario
        levers = parse_levers(q, eng.base["utilisation"])
        if not levers:
            levers = {"utilisation_target": 0.80}
            note = "No lever was recognised, so the default utilisation scenario (80%) was run. "
        else:
            note = ""
        r = eng.run(levers)
        inc, b, s = r["incremental"], r["base"], r["scenario"]
        lever_txt = ", ".join(f"{LEVERS[k][0].lower()} {pct(v) if LEVERS[k][5] == 'share' else money(v) if LEVERS[k][5] == 'USD' else f'{v:.0f} months'}"
                              for k, v in levers.items())
        answer = (note + f"Illustrative scenario ({lever_txt}): incremental cost {money(inc['cost'])}, incremental expected value "
                  f"{money(inc['value'])}, net {money(inc['net_value'])}" + (f", incremental ROI {pct(inc['roi'])}" if inc["roi"] is not None else "")
                  + (f", payback {inc['payback_months']:.1f} months" if inc["payback_months"] else "")
                  + f". Portfolio expected ROI moves from {pct(b['roi'], 1)} to {pct(s['roi'], 1)}.")
        if "utilisation_target" in levers:
            answer += (f" Raising utilisation from {pct(b['utilisation'])} to {pct(levers['utilisation_target'])} frees "
                       f"{inc['capacity_gpu_hours']:,.0f} GPU-hours a year for new workloads without buying infrastructure "
                       f"(about {money(inc['infrastructure_avoided'])} of capacity cost avoided).")
        return self.respond(
            q, "scenario", answer,
            key_drivers=[f"{x['label']}: value {money(x['value_change'])}, cost {money(x['cost_change'])}" + (f" ({x['note']})" if x["note"] else "") for x in r["bridge"]],
            numbers=[Number("Base investment", b["investment"]), Number("Base expected value", b["expected_value"], basis="assumption"),
                     Number("Scenario investment", s["investment"], basis="forecast"), Number("Scenario expected value", s["expected_value"], basis="forecast"),
                     Number("Incremental cost", inc["cost"], basis="forecast"), Number("Incremental value", inc["value"], basis="forecast"),
                     Number("Incremental ROI", inc["roi"], "ratio", basis="forecast", formula="(dValue - dCost) / dCost"),
                     Number("Incremental capacity", inc["capacity_gpu_hours"], "GPU-hours", display=f"{inc['capacity_gpu_hours']:,.0f} GPU-hours", basis="forecast"),
                     Number("Payback", inc["payback_months"], "months", display=f"{inc['payback_months']:.1f} months" if inc["payback_months"] else "n/a", basis="forecast"),
                     Number("Scenario net value", s["net_value"], basis="forecast")],
            evidence=[ds("infrastructure_usage", "Q4 capacity and GPU-hours, annualised"), ds("benefit_monthly"), ds("assumptions", "scenario assumptions A-33 to A-37")],
            assumptions=[{**a, "last_reviewed": None} for a in r["assumptions"]],
            confidence={"level": "Low", "basis": "Illustrative what-if on synthetic data using documented scenario conventions; not a forecast. Direction is more reliable than magnitude."},
            drilldown=[Drilldown("Open in Scenario Simulator", "scenario", "&".join(f"{k}={v}" for k, v in levers.items()))],
            table={"columns": ["lever", "label", "value_change", "cost_change"], "rows": r["bridge"]},
            follow_ups=["Which variables have the greatest impact on AI value?"])

    def sensitivity(self, q: str):
        rows = self.ctx.scenario.sensitivity()
        return self.respond(
            q, "sensitivity",
            f"{rows[0]['label']} has the largest impact on net AI value (swing {money(rows[0]['swing'])} for a ±20% change), "
            f"followed by {rows[1]['label']} ({money(rows[1]['swing'])}) and {rows[2]['label']} ({money(rows[2]['swing'])}).",
            key_drivers=[f"{r['label']}: {money(r['low'])} to {money(r['high'])}" for r in rows],
            numbers=[Number(f"{r['label']} swing", r["swing"], basis="forecast") for r in rows],
            evidence=[ds("assumptions"), ds("benefit_monthly")],
            confidence={"level": "Medium", "basis": "One-at-a-time sensitivity around the FY2026 expected-value base."},
            table={"columns": ["label", "low", "high", "swing"], "rows": rows},
            drilldown=[Drilldown("Open sensitivity analysis", "scenario", "sensitivity")])
