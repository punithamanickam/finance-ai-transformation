"""Executive Reporting Agent: CFO and board briefings assembled from the other agents' deterministic outputs."""
from __future__ import annotations

from src.agents.base import Agent, Drilldown, Number, calc
from src.copilot.response import money, pct
from src.reporting.briefing import build_briefing


class ReportingAgent(Agent):
    name = "Executive Reporting Agent"

    def briefing(self, q: str):
        b = build_briefing(self.ctx)
        k = self.ctx.kpis
        summary = b["sections"][0]["points"]
        return self.respond(
            q, "briefing", " ".join(summary[:2]),
            key_drivers=[f"{s['heading']}: {s['points'][0]}" for s in b["sections"][1:8] if s["points"]],
            numbers=[Number("Investment", k["total_investment"], evidence_id="kpi.total_investment"),
                     Number("Realised value", k["realised_value"], evidence_id="kpi.realised_value"),
                     Number("Expected value", k["expected_value"], evidence_id="kpi.expected_value", basis="assumption"),
                     Number("Realised ROI", k["realised_roi"], "ratio", evidence_id="kpi.realised_roi", basis="calculated"),
                     Number("At-risk initiatives", k["at_risk"], "count", evidence_id="kpi.at_risk", basis="calculated")],
            evidence=[calc("kpi.value_classification", "Value classification"), calc("analysis.roi_movement", "ROI movement")],
            confidence={"level": "High", "basis": "Every statement is generated from engine outputs; forecasts and scenarios are labelled."},
            drilldown=[Drilldown("Open the full CFO briefing", "report", "cfo")],
            table={"columns": ["heading", "points"], "rows": b["sections"]},
            follow_ups=["Why did AI ROI decline this quarter?", "Which benefits rely heavily on assumptions?"])

    def overview(self, q: str):
        k, t = self.ctx.kpis, self.ctx.table
        verdict = ("partly" if 0.4 <= k["benefit_realisation"] < 0.8 else "largely" if k["benefit_realisation"] >= 0.8 else "not yet")
        green = t[t.rag == "Green"]
        return self.respond(
            q, "overview",
            f"The evidence says {verdict}. {money(k['realised_value'])} of value is realised on {money(k['total_investment'])} invested "
            f"({pct(k['benefit_realisation'])} of expected; in-year ROI {pct(k['realised_roi'])}). {len(green)} initiatives deliver at or near plan, "
            f"while {k['at_risk']} are at risk. {money(k['validated_value'] + k['hypothetical_value'])} of the expected value is not yet evidenced.",
            key_drivers=[f"Performing: " + ", ".join(green.sort_values('realised_value', ascending=False)['name'].head(4)),
                         f"At risk: " + ", ".join(t[t.rag == 'Red']['name']),
                         f"Q4 infrastructure utilisation {pct(k['utilisation_q4'], 1)}",
                         f"Three-year NPV outlook {money(k['npv_3yr'])} (forecast)"],
            numbers=[Number("Investment", k["total_investment"], evidence_id="kpi.total_investment"), Number("Realised value", k["realised_value"], evidence_id="kpi.realised_value"),
                     Number("Expected value", k["expected_value"], basis="assumption", evidence_id="kpi.expected_value"),
                     Number("Benefit realisation", k["benefit_realisation"], "ratio", basis="calculated"),
                     Number("Realised ROI", k["realised_roi"], "ratio", basis="calculated"), Number("Expected ROI", k["expected_roi"], "ratio", basis="assumption")],
            evidence=[calc("kpi.value_classification", "Value classification"), calc("kpi.at_risk", "At-risk rules")],
            confidence={"level": "Medium", "basis": "Realised figures are evidenced; the expected figure and the NPV outlook depend on assumptions."},
            drilldown=[Drilldown("Show evidence", "evidence", "kpi.value_classification")] + self.ctx.ini_drill(t[t.rag == "Red"].initiative_id, 3),
            follow_ups=["How much value has actually been realised?", "Why is realised value below expected value?"])
