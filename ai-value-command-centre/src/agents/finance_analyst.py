"""Finance Analyst Agent: investment, spend, budget and forecast variance, cost growth, ROI movement, unit economics,
P&L reflection. All numbers come from the deterministic engines."""
from __future__ import annotations

from src.agents.base import Agent, Drilldown, Number, calc, ds
from src.copilot.response import money, pct, spct
from src.finance import formulas as F


class FinanceAnalystAgent(Agent):
    name = "Finance Analyst Agent"

    # ------------------------------------------------------------------
    def investment_total(self, q: str):
        k, t = self.ctx.kpis, self.ctx.table
        over = t[t.budget_variance_pct > 0.05].sort_values("budget_variance_pct", ascending=False)
        qtr = self.ctx.portfolio.quarterly()
        pc = self.ctx.repo.programme_costs
        groups = pc.groupby("cost_group").amount.sum().sort_values(ascending=False)
        top = t.sort_values("investment", ascending=False).head(3)
        return self.respond(
            q, "investment_total",
            f"FY2026 AI investment is {money(k['total_investment'])} across {k['initiatives']} initiatives, "
            f"{money(k['total_investment'] - k['budget'])} ({pct(k['budget_variance_pct'], 1)}) above the {money(k['budget'])} budget.",
            key_drivers=[f"{g} is {pct(v / groups.sum())} of spend ({money(v)})" for g, v in groups.head(3).items()]
            + [f"{len(over)} initiatives are more than 5% over budget, led by {over.iloc[0]['name']} ({pct(over.iloc[0].budget_variance_pct)})" if len(over) else "No initiative is more than 5% over budget",
               f"Quarterly spend: " + ", ".join(f"{r.quarter[-2:]} {money(r.investment)}" for r in qtr.itertuples()),
               f"Largest investments: " + ", ".join(f"{r['name']} {money(r.investment)}" for _, r in top.iterrows())],
            numbers=[Number("Total AI investment", k["total_investment"], evidence_id="kpi.total_investment", basis="actual"),
                     Number("Approved budget", k["budget"], basis="actual"),
                     Number("Budget variance", k["total_investment"] - k["budget"], formula=F.FORMULAS["budget_variance"], basis="calculated"),
                     Number("Q4 vs Q3 spend growth", k["ai_cost_growth_qoq"], "ratio", evidence_id="kpi.ai_cost_growth_qoq", basis="calculated")],
            evidence=[ds("cost_transactions", f"{len(pc):,} programme cost transactions"), ds("budgets"), calc("kpi.total_investment", "Total investment calculation")],
            confidence={"level": "High", "basis": "Sum of programme cost transactions; reconciles to initiative totals and the budget table. No assumptions involved."},
            drilldown=self.ctx.ini_drill(top.initiative_id) + [Drilldown("Investment calculation", "evidence", "kpi.total_investment")],
            follow_ups=["Where is the AI money going?", "Which initiatives have the largest budget variance?"])

    def spend_breakdown(self, q: str):
        pc, t = self.ctx.repo.programme_costs, self.ctx.table
        total = pc.amount.sum()
        groups = pc.groupby("cost_group").amount.sum().sort_values(ascending=False)
        cat = t.groupby("hpe_category").investment.sum().sort_values(ascending=False)
        bu = t.groupby("business_unit").investment.sum().sort_values(ascending=False)
        vendors = self.ctx.costs.by_vendor()
        return self.respond(
            q, "spend_breakdown",
            f"Of {money(total)} FY2026 AI spend, {pct(groups.iloc[0] / total)} went to {groups.index[0].lower()}, "
            f"{pct(groups.iloc[1] / total)} to {groups.index[1].lower()} and {pct(groups.iloc[2] / total)} to {groups.index[2].lower()}. "
            f"By HPE portfolio category, {cat.index[0]} carries the most investment ({money(cat.iloc[0])}).",
            key_drivers=[f"By cost group: " + ", ".join(f"{g} {money(v)}" for g, v in groups.items()),
                         f"By business unit: " + ", ".join(f"{b} {money(v)}" for b, v in bu.head(4).items()),
                         f"By HPE category: " + ", ".join(f"{c} {money(v)}" for c, v in cat.items()),
                         f"Largest vendors: " + ", ".join(f"{v['vendor']} {money(v['amount'])}" for v in vendors[:3])],
            numbers=[Number(f"{g}", v, evidence_id=f"waterfall.cost.{g}") for g, v in groups.items()],
            evidence=[ds("cost_transactions"), ds("vendors"), ds("ai_initiatives", "HPE category mapping")],
            confidence={"level": "High", "basis": "Direct aggregation of cost transactions by category, business unit and vendor."},
            drilldown=[Drilldown(f"{g} spend", "evidence", f"waterfall.cost.{g}") for g in groups.index[:3]],
            table={"columns": ["cost_group", "amount", "share"], "rows": [{"cost_group": g, "amount": float(v), "share": float(v / total)} for g, v in groups.items()]},
            follow_ups=["What is driving AI cost growth?", "Which business units have the highest AI spend?"])

    def bu_spend(self, q: str):
        rows = self.ctx.costs.by_business_unit()
        top = rows[0]
        return self.respond(
            q, "bu_spend",
            f"{top['business_unit']} has the highest AI spend at {money(top['investment'])} across {top['initiatives']} initiative(s), "
            f"with a realised ROI of {pct(top['realised_roi'])}.",
            key_drivers=[f"{r['business_unit']}: {money(r['investment'])} spend, {money(r['realised_value'])} realised value, ROI {pct(r['realised_roi'])}" for r in rows],
            numbers=[Number(r["business_unit"], r["investment"], basis="actual") for r in rows],
            evidence=[ds("cost_transactions"), ds("business_units"), ds("benefit_monthly")],
            confidence={"level": "High", "basis": "Spend is actual; realised value uses evidenced benefits only."},
            table={"columns": ["business_unit", "investment", "realised_value", "expected_value", "realised_roi"], "rows": rows},
            drilldown=self.ctx.ini_drill(self.ctx.table.sort_values("investment", ascending=False).initiative_id, 3),
            follow_ups=["Which initiatives have the largest budget variance?"])

    def budget_variance(self, q: str):
        t = self.ctx.table.sort_values("budget_variance", ascending=False)
        sig = t[t.budget_variance_pct.abs() > 0.05]
        top = t.iloc[0]
        det = self.ctx.portfolio.initiative_detail(top.initiative_id)
        cats = sorted(det["cost_by_category"], key=lambda c: -c["variance"])[:3]
        return self.respond(
            q, "budget_variance",
            f"{len(sig)} initiatives are more than 5% away from budget. The largest overspend is {top['name']}: "
            f"{money(top.actual_spend)} against {money(top.budget)} ({spct(top.budget_variance_pct)}), driven by "
            + ", ".join(f"{c['category']} {money(c['variance'])}" for c in cats) + ".",
            key_drivers=[f"{r['name']}: {spct(r.budget_variance_pct)} ({money(r.budget_variance)})" for _, r in sig.iterrows()]
            + [f"Portfolio: {money(self.ctx.kpis['total_investment'] - self.ctx.kpis['budget'])} over budget ({pct(self.ctx.kpis['budget_variance_pct'], 1)})"],
            numbers=[Number(f"{r['name']} variance", r.budget_variance, formula=F.FORMULAS["budget_variance"], basis="calculated",
                            evidence_id=f"initiative.{r.initiative_id}") for _, r in sig.iterrows()],
            evidence=[ds("cost_transactions"), ds("budgets"), ds("forecasts", "FY26 Q3 re-forecast")],
            confidence={"level": "High", "basis": "Actual cost transactions compared with the approved monthly budget; no assumptions."},
            table={"columns": ["initiative_id", "name", "budget", "actual_spend", "budget_variance", "budget_variance_pct", "forecast_variance_pct"],
                   "rows": [{c: (float(r[c]) if not isinstance(r[c], str) else r[c]) for c in ["initiative_id", "name", "budget", "actual_spend", "budget_variance", "budget_variance_pct", "forecast_variance_pct"]} for _, r in t.iterrows()]},
            drilldown=self.ctx.ini_drill(sig.initiative_id),
            follow_ups=[f"Tell me about {top['name']}", "What is driving AI cost growth?"])

    def cost_growth(self, q: str):
        g = self.ctx.costs.cost_growth_drivers()
        m = self.ctx.portfolio.roi_movement()
        infra = m["cost_groups"]["Infrastructure"]
        cloud = m["cost_groups"]["Cloud"]
        top = g["top_movements"][:3]
        return self.respond(
            q, "cost_growth",
            f"AI spend rose {pct(g['growth'], 1)} from {money(g['q3'])} in FY26-Q3 to {money(g['q4'])} in FY26-Q4. "
            f"Infrastructure cost grew {pct(infra['change_pct'])} and cloud {pct(cloud['change_pct'])}, while GPU utilisation fell from "
            f"{pct(m['utilisation_from'], 1)} to {pct(m['utilisation_to'], 1)} as installed capacity rose {pct(m['capacity_change_pct'])}.",
            key_drivers=[f"{c['label']}: {money(c['change'])} ({pct(c['change_pct'])})" for c in g["by_category"][:3] if c["change"] > 0]
            + [f"{x['name']} {x['category']}: +{money(x['change'])}" for x in top]
            + ["Capacity was added ahead of workload demand, so cost per used GPU-hour rose"],
            numbers=[Number("FY26-Q3 spend", g["q3"]), Number("FY26-Q4 spend", g["q4"]),
                     Number("Quarter-on-quarter growth", g["growth"], "ratio", basis="calculated", evidence_id="kpi.ai_cost_growth_qoq"),
                     Number("Infrastructure cost growth", infra["change_pct"], "ratio", basis="calculated"),
                     Number("GPU utilisation Q3", m["utilisation_from"], "ratio"), Number("GPU utilisation Q4", m["utilisation_to"], "ratio")],
            evidence=[ds("cost_transactions"), ds("infrastructure_usage", "GPU capacity and hours used by cluster")],
            confidence={"level": "High", "basis": "Cost movements are actual transactions; utilisation is metered GPU-hours against installed capacity."},
            drilldown=self.ctx.ini_drill([x["initiative_id"] for x in top]) + [Drilldown("GPU cost", "cost", "cost.gpu")],
            follow_ups=["What happens if infrastructure utilisation increases from 63% to 80%?"])

    def roi_movement(self, q: str):
        m = self.ctx.portfolio.roi_movement()
        t = self.ctx.table.set_index("initiative_id")
        worst = m["initiatives"][0]
        w = t.loc[worst["initiative_id"]]
        second = m["initiatives"][1]
        infra = m["cost_groups"]["Infrastructure"]
        direction = "fell" if m["change_pp"] < 0 else "rose"
        drivers = [f"AI infrastructure cost {'increased' if infra['change_pct'] > 0 else 'decreased'} {pct(abs(infra['change_pct']))}",
                   f"Infrastructure utilisation declined from {pct(m['utilisation_from'], 1)} to {pct(m['utilisation_to'], 1)} "
                   f"({pct((m['utilisation_to'] - m['utilisation_from']) / m['utilisation_from'])}) as capacity grew {pct(m['capacity_change_pct'])}"]
        for d in m["delayed_initiatives"]:
            if d["schedule_slip_months"] >= 2:
                drivers.append(f"{d['name']} benefits were delayed: go-live {int(d['schedule_slip_months'])} months late")
        for r in m["value_per_unit_revisions"]:
            drivers.append(f"{r['name']} value per active user fell {pct(abs(r['value_per_user_change']))}: the revenue assumption was revised")
        lag = m["validated_pending"]
        if lag["to"] > lag["from"]:
            drivers.append(f"Owner-validated benefit awaiting evidence rose from {money(lag['from'])} to {money(lag['to'])}")
        return self.respond(
            q, "roi_movement",
            f"AI portfolio ROI {direction} {abs(m['change_pp']):.1f} percentage points, from {pct(m['roi_from'], 1)} in {m['from']} "
            f"to {pct(m['roi_to'], 1)} in {m['to']}. Cost growth explains {m['cost_effect_pp']:+.1f} pp and lower value "
            f"{m['value_effect_pp']:+.1f} pp. The largest contributor is {worst['name']} ({worst['contribution_pp']:+.1f} pp), "
            f"followed by {second['name']} ({second['contribution_pp']:+.1f} pp).",
            key_drivers=drivers,
            numbers=[Number(f"ROI {m['from']}", m["roi_from"], "ratio", formula=F.FORMULAS["roi"], basis="calculated"),
                     Number(f"ROI {m['to']}", m["roi_to"], "ratio", formula=F.FORMULAS["roi"], basis="calculated"),
                     Number("Change", m["change_pp"], "pp", evidence_id="analysis.roi_movement", basis="calculated",
                            formula="dROI = (V2-V1)/C2 + V1(1/C2-1/C1)"),
                     Number("Cost effect", m["cost_effect_pp"], "pp", basis="calculated"),
                     Number("Value effect", m["value_effect_pp"], "pp", basis="calculated"),
                     Number(f"Largest contributor: {worst['name']} investment", float(w.investment), evidence_id=f"initiative.{worst['initiative_id']}"),
                     Number("Realised benefit", float(w.realised_value)), Number("Expected benefit", float(w.expected_value), basis="assumption"),
                     Number("Benefit realisation", w.benefit_realisation, "ratio", basis="calculated"),
                     Number("Budget variance", w.budget_variance_pct, "ratio", basis="calculated")],
            evidence=[calc("analysis.roi_movement", "ROI movement decomposition", "contributions by initiative sum exactly to the change"),
                      ds("cost_transactions"), ds("benefit_monthly"), ds("infrastructure_usage"), ds("ai_usage")],
            assumptions=self.ctx.assumptions([a for a in str(self.ctx.repo["benefits"].set_index("initiative_id").assumption_ids.get(worst["initiative_id"], "")).split(",") if a]),
            confidence={"level": "High", "basis": "Quarterly ROI uses realised (evidenced) value and actual spend; the decomposition is exact. "
                        "Driver attributions (delay, revision) are read from milestones and usage data."},
            drilldown=[Drilldown("Show evidence", "evidence", "analysis.roi_movement")] + self.ctx.ini_drill([x["initiative_id"] for x in m["initiatives"][:3]]),
            table={"columns": ["initiative_id", "name", "contribution_pp", "value_change", "cost_change"], "rows": m["initiatives"]},
            follow_ups=[f"Tell me about {worst['name']}", "What is driving AI cost growth?"])

    def unit_economics(self, q: str):
        u = self.ctx.costs.unit_economics()
        m = u["metrics"]
        labels = {"ai_cost_per_employee": "AI cost per employee", "ai_cost_per_customer": "AI cost per customer",
                  "ai_cost_per_active_user": "AI cost per active user", "ai_cost_per_transaction": "AI cost per transaction",
                  "ai_cost_per_interaction": "AI cost per AI interaction", "ai_cost_per_gpu_hour_used": "Infrastructure cost per used GPU-hour",
                  "ai_cost_per_dollar_revenue": "AI cost per $1 of incremental revenue margin",
                  "ai_cost_per_dollar_savings": "AI cost per $1 of savings", "value_per_dollar_invested": "AI value per $1 invested"}
        nums = [Number(labels[k], v, "USD" if k != "value_per_dollar_invested" else "ratio", evidence_id=f"unit.{k}", basis="calculated",
                       display=(f"${v:,.2f}" if k != "value_per_dollar_invested" else f"${v:,.2f}") if v is not None else "n/a")
                for k, v in m.items()]
        best = sorted([x for x in u["by_initiative"] if x["value_per_dollar"] is not None], key=lambda x: -x["value_per_dollar"])
        return self.respond(
            q, "unit_economics",
            f"Each $1 invested has returned ${m['value_per_dollar_invested']:.2f} of realised value so far. AI costs "
            f"${m['ai_cost_per_employee']:,.0f} per employee and ${m['ai_cost_per_interaction']:.2f} per AI interaction; "
            f"every $1 of realised savings cost ${m['ai_cost_per_dollar_savings']:.2f}.",
            key_drivers=[f"Best value per $1: " + ", ".join(f"{x['name']} ${x['value_per_dollar']:.2f}" for x in best[:3]),
                         f"Weakest value per $1: " + ", ".join(f"{x['name']} ${x['value_per_dollar']:.2f}" for x in best[-3:])] + u["notes"],
            numbers=nums,
            evidence=[ds("cost_transactions"), ds("ai_usage"), ds("companies", "employees and customers"), ds("infrastructure_usage")],
            confidence={"level": "High", "basis": "Ratios of actual costs to metered usage; revenue and savings use evidenced benefits only."},
            table={"columns": ["name", "transaction_type", "cost_per_transaction", "cost_per_active_user", "value_per_dollar"], "rows": u["by_initiative"]},
            drilldown=self.ctx.ini_drill([x["initiative_id"] for x in best[:3]]),
            follow_ups=["Where is the AI money going?"])

    def pnl_share(self, q: str):
        p = self.ctx.benefits.pnl_reflection()
        k = self.ctx.kpis
        return self.respond(
            q, "pnl_share",
            f"{pct(p['share_of_realised_in_pnl'])} of realised AI benefit ({money(p['financial_realised'])}) is visible in the P&L as "
            f"GL-evidenced cost reduction or margin. That is {pct(p['share_of_expected_in_pnl'])} of the {money(p['business_case'])} "
            f"business-case benefit. A further {money(p['operational_realised'])} is realised operationally (hours released) but not in the P&L.",
            key_drivers=[f"Financial (GL-backed) realised benefit: {money(p['financial_realised'])}",
                         f"Operational realised benefit (productivity, telemetry): {money(p['operational_realised'])}. It becomes P&L value only if capacity is redeployed or costs removed",
                         f"Validated but not yet in actuals: {money(p['validated'])}",
                         f"Hypothetical (business case only): {money(p['hypothetical'])}",
                         "P&L tagging reconciles to benefit records" if p["reconciles"] else "P&L tagging does NOT reconcile to benefit records"],
            numbers=[Number("Share of realised benefit in P&L", p["share_of_realised_in_pnl"], "ratio", basis="calculated"),
                     Number("Share of expected benefit in P&L", p["share_of_expected_in_pnl"], "ratio", basis="calculated"),
                     Number("GL-evidenced benefit", p["financial_realised"]), Number("Operational benefit", p["operational_realised"]),
                     Number("P&L-tagged AI benefit", p["pnl_tagged_benefit"], formula="SUM(financials.ai_attributed_benefit)")],
            evidence=[ds("financials", "ai_attributed_benefit column, 24 months"), ds("benefit_evidence"), ds("benefit_monthly")],
            confidence={"level": "High", "basis": "GL-evidenced benefit reconciles to the P&L tags in the financials table."},
            drilldown=[Drilldown("Value classification", "evidence", "kpi.value_classification")],
            follow_ups=["Which benefits rely heavily on assumptions?"])

