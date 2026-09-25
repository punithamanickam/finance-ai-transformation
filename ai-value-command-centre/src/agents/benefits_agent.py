"""Benefits Agent: realised vs expected value, benefits leakage, assumption dependency and confidence."""
from __future__ import annotations

import re

from src.agents.base import Agent, Drilldown, Number, calc, ds
from src.copilot.response import money, pct
from src.finance import formulas as F
from src.finance.confidence import DISCLAIMER, METHOD_LABEL
from src.finance.portfolio import BENEFIT_TYPES


class BenefitsAgent(Agent):
    name = "Benefits Agent"

    def realised_value(self, q: str):
        k, t = self.ctx.kpis, self.ctx.table
        p = self.ctx.benefits.pnl_reflection()
        top = t.sort_values("realised_value", ascending=False).head(3)
        by_type = {BENEFIT_TYPES[b]: float(t[f"realised_{b}"].sum()) for b in BENEFIT_TYPES}
        return self.respond(
            q, "realised_value",
            f"Realised AI value is {money(k['realised_value'])}, {pct(k['benefit_realisation'])} of the {money(k['expected_value'])} expected. "
            f"A further {money(k['validated_value'])} is validated by business owners but not yet evidenced in actuals, and "
            f"{money(k['hypothetical_value'])} rests on business-case assumptions. Against {money(k['total_investment'])} invested, "
            f"realised ROI is {pct(k['realised_roi'])} (expected {pct(k['expected_roi'])}).",
            key_drivers=[f"Realised by type: " + ", ".join(f"{a} {money(b)}" for a, b in by_type.items() if b),
                         f"Top contributors: " + ", ".join(f"{r['name']} {money(r.realised_value)}" for _, r in top.iterrows()),
                         f"{pct(p['share_of_realised_in_pnl'])} of realised benefit is GL-evidenced in the P&L; the rest is operational (hours released)",
                         f"Realised value is net of {money(float(t.incremental_opex_actual.sum()))} incremental operating cost"],
            numbers=[Number("Realised value", k["realised_value"], evidence_id="kpi.realised_value"),
                     Number("Expected value", k["expected_value"], evidence_id="kpi.expected_value", basis="assumption"),
                     Number("Validated value", k["validated_value"], basis="validated"), Number("Hypothetical value", k["hypothetical_value"], basis="assumption"),
                     Number("Benefit realisation", k["benefit_realisation"], "ratio", formula=F.FORMULAS["benefit_realisation"], evidence_id="kpi.benefit_realisation", basis="calculated"),
                     Number("Realised ROI", k["realised_roi"], "ratio", formula=F.FORMULAS["roi"], evidence_id="kpi.realised_roi", basis="calculated"),
                     Number("Value per $1 invested", k["value_per_dollar"], "ratio", display=f"${k['value_per_dollar']:.2f}", basis="calculated")],
            evidence=[calc("kpi.realised_value", "Realised value calculation"), calc("kpi.value_classification", "Realised / validated / hypothetical split"),
                      ds("benefit_monthly"), ds("benefit_evidence")],
            confidence={"level": "High", "basis": "Realised value counts only benefits backed by GL or telemetry evidence. Validated and hypothetical amounts are shown separately and not counted."},
            drilldown=[Drilldown("Show evidence", "evidence", "kpi.realised_value")] + self.ctx.ini_drill(top.initiative_id, 3),
            follow_ups=["Why is realised value below expected value?", "What percentage of AI value is actually reflected in the P&L?"])

    def value_gap(self, q: str):
        ls = self.ctx.benefits.leakage_summary()
        reasons = [r for r in ls["reasons"] if r["value"] > 1]
        top = ls["by_initiative"][:4]
        k = self.ctx.kpis
        return self.respond(
            q, "value_gap",
            f"Realised benefit is {money(ls['unrealised'])} short of the {money(ls['business_case'])} gross business-case benefit (before incremental operating cost). "
            f"The largest causes are {reasons[0]['label'].lower()} ({money(reasons[0]['value'])}), {reasons[1]['label'].lower()} "
            f"({money(reasons[1]['value'])}) and {reasons[2]['label'].lower()} ({money(reasons[2]['value'])}). "
            f"{top[0]['name']} accounts for the biggest single gap ({money(top[0]['unrealised'])}, mainly {top[0]['primary_reason'].lower()}).",
            key_drivers=[f"{r['label']}: {money(r['value'])}" for r in ls["reasons"]]
            + [f"Cost overruns in business run costs: {money(ls['cost_overruns'])} (reduces net value)"]
            + [f"{x['name']}: {money(x['unrealised'])} unrealised, mainly {x['primary_reason'].lower()}" for x in top],
            numbers=[Number("Business-case benefit", ls["business_case"], basis="assumption"), Number("Realised benefit", ls["realised"]),
                     Number("Unrealised", ls["unrealised"], basis="calculated")]
            + [Number(r["label"], r["value"], basis="calculated") for r in ls["reasons"]],
            evidence=[calc("kpi.value_classification", "Value classification"), ds("benefit_monthly"), ds("ai_usage", "planned vs actual active users"),
                      ds("milestones", "planned vs actual go-live"), ds("benefit_evidence")],
            assumptions=[{"assumption_id": "method", "description": ls["method"], "value": None, "unit": "", "source": "Benefits engine"}],
            confidence={"level": "Medium", "basis": "Delay and adoption effects are computed from milestones and usage. The value-per-unit residual is labelled with the owner's reason code, which is a judgement."},
            drilldown=self.ctx.ini_drill([x["initiative_id"] for x in top]) + [Drilldown("Benefit realisation view", "benefit", "all")],
            table={"columns": ["name", "business_case", "realised", "unrealised", "primary_reason"], "rows": [{k2: x[k2] for k2 in ("name", "business_case", "realised", "unrealised", "primary_reason")} for x in ls["by_initiative"]]},
            follow_ups=[f"Tell me about {top[0]['name']}", "Which benefits rely heavily on assumptions?"])

    def below_plan(self, q: str):
        rows = [r for r in self.ctx.benefits.realisation_table() if r["realisation"] is not None and r["realisation"] < 0.7]
        rows.sort(key=lambda r: -r["gap"])
        return self.respond(
            q, "below_plan",
            f"{len(rows)} benefit lines are below 70% of plan, a combined gap of {money(sum(r['gap'] for r in rows))}. The largest is "
            f"{rows[0]['initiative_name']}: {rows[0]['description'].lower()} ({pct(rows[0]['realisation'])} realised)." if rows else "No benefit line is below 70% of plan.",
            key_drivers=[f"{r['initiative_name']}: {r['description']} at {pct(r['realisation'])} (gap {money(r['gap'])}; "
                         f"delay {money(r['delayed_implementation'])}, adoption {money(r['low_adoption'])}, pending validation {money(r['pending_validation'])})" for r in rows[:6]],
            numbers=[Number(r["benefit_id"], r["gap"], basis="calculated", evidence_id=f"benefit.{r['benefit_id']}") for r in rows[:6]],
            evidence=[ds("benefits"), ds("benefit_monthly"), ds("benefit_evidence")],
            confidence={"level": "High", "basis": "Realisation compares evidenced benefit with the approved business case per line."},
            drilldown=[Drilldown(f"{r['benefit_id']} {r['initiative_name']}", "benefit", r["benefit_id"]) for r in rows[:5]],
            table={"columns": ["benefit_id", "initiative_name", "description", "business_case", "realised", "gap", "realisation", "confidence"], "rows": rows},
            follow_ups=["Why is realised value below expected value?"])

    def assumption_heavy(self, q: str):
        rows = self.ctx.benefits.assumption_dependency()
        heavy = [r for r in rows if r["assumption_share"] >= 0.4]
        ids = sorted({a["assumption_id"] for r in heavy for a in r["assumptions"]})
        names = self.ctx.table.set_index("initiative_id")["name"]
        return self.respond(
            q, "assumption_heavy",
            f"{len(heavy)} benefit lines depend on assumptions for at least 40% of their expected value, "
            f"{money(sum(r['expected'] for r in heavy))} of business case in total. The most exposed is {names[heavy[0]['initiative_id']]}: "
            f"{heavy[0]['description'].lower()} ({pct(heavy[0]['assumption_share'])} assumption-based, measured by {METHOD_LABEL[heavy[0]['methodology']]})." if heavy
            else "No benefit line relies on assumptions for 40% or more of its value.",
            key_drivers=[f"{names[r['initiative_id']]}: {r['description']} ({pct(r['assumption_share'])} assumption-based; {METHOD_LABEL[r['methodology']]}; confidence {r['confidence']:.0f}/100)" for r in heavy[:7]],
            numbers=[Number(f"{r['benefit_id']} assumption share", r["assumption_share"], "ratio", basis="calculated",
                            formula="(hypothetical + 0.5 x validated) / expected", evidence_id=f"confidence.{r['benefit_id']}") for r in heavy[:7]],
            evidence=[ds("assumptions"), ds("benefits", "methodology and validation flags"), ds("benefit_evidence")],
            assumptions=self.ctx.assumptions(ids),
            confidence={"level": "High", "basis": "Assumption share is computed from the value classification; the assumptions themselves are listed with source and review date."},
            drilldown=[Drilldown(f"{r['benefit_id']} {names[r['initiative_id']]}", "benefit", r["benefit_id"]) for r in heavy[:5]],
            table={"columns": ["benefit_id", "description", "expected", "hypothetical", "validated", "assumption_share", "methodology", "confidence"],
                   "rows": [{k2: r[k2] for k2 in ("benefit_id", "description", "expected", "hypothetical", "validated", "assumption_share", "methodology", "confidence")} for r in rows]},
            follow_ups=["What happens if the benefit realisation rate is 80%?"])

    def explain_expected(self, q: str):
        k, t = self.ctx.kpis, self.ctx.table
        comps = [(BENEFIT_TYPES[b], float(t[f"expected_{b}"].sum())) for b in BENEFIT_TYPES]
        opex = float(t.incremental_opex_plan.sum())
        ids = sorted({a for s in self.ctx.repo["benefits"].assumption_ids.dropna() for a in s.split(",")})
        quoted = re.search(r"\$\s?(\d+(?:\.\d+)?)\s?m", q.lower())
        note = (f" (The figure in the question, ${quoted.group(1)}M, differs from the calculated {money(k['expected_value'])}; "
                f"the calculated figure is used.)" if quoted and abs(float(quoted.group(1)) * 1e6 - k["expected_value"]) > 50_000 else "")
        return self.respond(
            q, "explain_expected",
            f"The {money(k['expected_value'])} expected AI value is the approved FY2026 business case: "
            + ", ".join(f"{a.lower()} {money(b)}" for a, b in comps if b) + f", less {money(opex)} planned incremental operating cost. "
            f"Of it, {money(k['realised_value'])} is realised, {money(k['validated_value'])} validated and {money(k['hypothetical_value'])} hypothetical." + note,
            key_drivers=[f"{a}: {money(b)}" for a, b in comps if b] + [f"Incremental operating cost: -{money(opex)}", f"Total: {money(k['expected_value'])}",
                         f"It rests on {len(ids)} documented business-case assumptions (listed below)"],
            numbers=[Number(a, b, basis="assumption") for a, b in comps if b] + [Number("Incremental operating cost", -opex, basis="assumption"),
                     Number("Expected value", k["expected_value"], evidence_id="kpi.expected_value", basis="assumption",
                            formula="Business-case benefit - planned incremental operating cost")],
            evidence=[calc("kpi.expected_value", "Expected value calculation"), ds("benefit_monthly", "business_case_value"),
                      ds("ai_initiatives", "incremental_opex_plan"), ds("assumptions")],
            assumptions=self.ctx.assumptions(ids),
            confidence={"level": "Medium", "basis": f"The arithmetic is exact, but the figure is a business-case target and "
                        f"{pct((k['validated_value'] + k['hypothetical_value']) / k['expected_value'])} of it is not yet evidenced."},
            drilldown=[Drilldown("Show calculation", "evidence", "kpi.expected_value")] + [Drilldown(f"{a} breakdown", "evidence", f"waterfall.benefit.{b}") for b, a in BENEFIT_TYPES.items()],
            follow_ups=["Which benefits rely heavily on assumptions?"])

    def confidence(self, q: str):
        summaries = self.ctx.benefits.by_type()
        s = sorted(summaries, key=lambda x: -(x["expected"] or 0))
        main = next((x for x in s if x["label"].lower().split()[0] in q.lower()), s[0])
        ev = main["evidence"]
        return self.respond(
            q, "confidence",
            f"{main['label']}: {money(main['expected'])} expected, {money(main['realised'])} realised, confidence {main['score']:.0f}/100 ({main['band']}). "
            f"Evidence: {ev['finance_validated_lines']} finance-validated lines, {ev['management_estimated_lines']} management-estimated, "
            f"{ev['gl_backed_lines']} GL-backed and {ev['telemetry_backed_lines']} telemetry-backed, across {ev['initiatives']} initiatives.",
            key_drivers=[f"{x['label']}: {x['score']:.0f}/100 ({x['band']}) on {money(x['expected'])}" for x in s] + [DISCLAIMER],
            numbers=[Number(f"{x['label']} confidence", x["score"], "score", display=f"{x['score']:.0f}/100", basis="calculated") for x in s],
            evidence=[ds("benefit_evidence"), ds("benefits", "validation flags and methodology")],
            confidence={"level": main["band"], "basis": "Eight weighted evidence factors: source quality, actual vs forecast, financial validation, completeness, owner confirmation, methodology, recency, assumption dependency."},
            drilldown=[Drilldown("Evidence & Trust Center", "evidence", "kpi.value_classification")],
            follow_ups=["Which benefits rely heavily on assumptions?"])
