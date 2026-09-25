"""Portfolio Analyst Agent: initiatives, status, at-risk derivation, drill-downs and natural-language data queries."""
from __future__ import annotations

from src.agents.base import Agent, Drilldown, Number, calc, ds
from src.copilot.response import money, pct, spct
from src.db.database import ensure_database
from src.finance.portfolio import RISK_RULES
from src.query import semantic_layer as Q


class PortfolioAnalystAgent(Agent):
    name = "Portfolio Analyst Agent"

    def data_query(self, q: str):
        spec = Q.parse(q)
        sql, params = Q.render(spec, self.ctx.bu_scope)
        rows = Q.execute(ensure_database(), sql, params)
        model = Q.SEMANTIC_MODEL[spec.entity]
        money_cols = [c for c in spec.fields if model["fields"].get(c) == "money"]
        key = "investment" if "investment" in spec.fields else (money_cols[0] if money_cols else None)
        total = sum((r.get(key) or 0) for r in rows) if key else None
        ids = [r["initiative_id"] for r in rows if r.get("initiative_id")]
        answer = f"{len(rows)} {model['label']} match: {Q.describe(spec)}."
        if rows and key:
            answer += f" Combined {key.replace('_', ' ')}: {money(total)}."
        if rows and spec.entity == "initiatives":
            answer += " " + "; ".join(f"{r['name']} ({money(r.get('investment'))}, realisation {pct(r.get('benefit_realisation'))})" for r in rows[:5]) + "."
        return self.respond(
            q, "data_query", answer,
            key_drivers=[f"Filter: {f.field} {f.op} {f.value}" for f in spec.filters] or ["No filters: all rows in scope"],
            numbers=[Number(f"Total {key.replace('_', ' ')}", total, basis="actual")] if key else [],
            evidence=[ds(model["view"], "materialised semantic view computed by the finance engine")],
            confidence={"level": "High", "basis": "Direct read-only query over the semantic layer; SQL shown below."},
            query={"sql": sql, "params": params, "spec": spec.to_dict()},
            table={"columns": spec.fields, "rows": rows},
            drilldown=self.ctx.ini_drill(dict.fromkeys(ids)),
            follow_ups=["Which initiatives are at risk?"])

    def at_risk(self, q: str):
        t = self.ctx.table
        red, amber = t[t.rag == "Red"], t[t.rag == "Amber"]
        rules = "; ".join(f"{v[0].lower()} (red if beyond {v[1]})" for v in RISK_RULES.values())
        return self.respond(
            q, "at_risk",
            f"{len(red)} of {len(t)} initiatives are at risk (red) and {len(amber)} are on watch (amber). The at-risk group holds "
            f"{money(red.investment.sum())} of investment and {money(red.expected_value.sum() - red.realised_value.sum())} of unrealised expected value.",
            key_drivers=[f"{r['name']}: " + ", ".join(f["detail"] for f in r.risk_flags) for _, r in red.iterrows()]
            + [f"Watch: {r['name']}: " + ", ".join(f["detail"] for f in r.risk_flags) for _, r in amber.iterrows()],
            numbers=[Number("At-risk initiatives", len(red), "count", evidence_id="kpi.at_risk", basis="calculated"),
                     Number("Investment at risk", float(red.investment.sum())),
                     Number("Unrealised expected value (at-risk)", float(red.expected_value.sum() - red.realised_value.sum()), basis="calculated")],
            evidence=[calc("kpi.at_risk", "At-risk rule evaluation", rules), ds("ai_usage"), ds("milestones"), ds("budgets")],
            confidence={"level": "High", "basis": f"Derived from data with documented rules, not hard-coded: {rules}."},
            drilldown=self.ctx.ini_drill(red.initiative_id),
            follow_ups=["Why is realised value below expected value?"])

    def initiative_detail(self, q: str, initiative_id: str):
        d = self.ctx.portfolio.initiative_detail(initiative_id)
        if d is None:
            return self.respond(q, "initiative_detail", f"{initiative_id} is not in your data scope.",
                                confidence={"level": "High", "basis": "Role-based scope applied."})
        i = d["initiative"]
        lk = [x for x in self.ctx.benefits.leakage_summary()["by_initiative"] if x["initiative_id"] == initiative_id]
        comp = lk[0]["components"] if lk else {}
        top_reasons = sorted(comp.items(), key=lambda kv: -kv[1])[:3]
        overs = sorted(d["cost_by_category"], key=lambda c: -c["variance"])[:2]
        return self.respond(
            q, "initiative_detail",
            f"{i['name']} ({i['business_unit']}, {i['hpe_category']}) has invested {money(i['investment'])} against a {money(i['budget'])} budget "
            f"({spct(i['budget_variance_pct'])}). It has realised {money(i['realised_value'])} of {money(i['expected_value'])} expected value "
            f"({pct(i['benefit_realisation'])}), with {money(i['validated_value'])} validated but not yet in actuals. Status: {i['rag']}.",
            key_drivers=[f["label"] + ": " + f["detail"] for f in i["risk_flags"]]
            + [f"Unrealised value driver: {k.replace('_', ' ')} {money(v)}" for k, v in top_reasons if v > 0]
            + [f"Largest cost variance: {c['category']} {money(c['variance'])}" for c in overs if c["variance"] > 0]
            + [f"Adoption {pct(i['adoption_rate'])} of target users vs {pct(i['adoption_target'])} planned"],
            numbers=[Number("Investment", i["investment"], evidence_id=f"initiative.{initiative_id}"), Number("Budget", i["budget"]),
                     Number("Expected value", i["expected_value"], basis="assumption"), Number("Realised value", i["realised_value"]),
                     Number("Validated value", i["validated_value"], basis="validated"), Number("Benefit realisation", i["benefit_realisation"], "ratio", basis="calculated"),
                     Number("Realised ROI", i["realised_roi"], "ratio", basis="calculated"),
                     Number("3-year NPV (outlook)", i["npv_3yr"], basis="forecast"),
                     Number("Confidence", i["confidence"], "score", display=f"{i['confidence']:.0f}/100 ({i['confidence_band']})")],
            evidence=[calc(f"initiative.{initiative_id}", "Initiative calculation"), ds("cost_transactions", f"initiative_id = {initiative_id}"),
                      ds("benefit_monthly", f"initiative_id = {initiative_id}"), ds("milestones"), ds("risks")],
            assumptions=self.ctx.assumptions(sorted({a for b in d["benefit_lines"] for a in str(b.get("assumption_ids") or "").split(",") if a})),
            confidence={"level": i["confidence_band"], "basis": f"Evidence-quality score {i['confidence']:.0f}/100 across its benefit lines."},
            drilldown=[Drilldown("Show evidence", "evidence", f"initiative.{initiative_id}")]
            + [Drilldown(f"Benefit {b['benefit_id']}", "benefit", b["benefit_id"]) for b in d["benefit_lines"]],
            follow_ups=["Why did AI ROI decline this quarter?", "Which benefits rely heavily on assumptions?"])
