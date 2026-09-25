"""Portfolio, value and ROI analytics. Every figure is computed from the transaction tables with the formulas in
`formulas.py`, and every headline figure is registered as an evidence record (formula, components, datasets, query,
assumptions) so the UI's "Explain" action and the copilot can show exactly how it was produced.

Value definitions (FY2026, 12 months to 31 Aug 2026)
* Investment          = programme spend (cost_transactions where cost_type = 'programme').
* Expected value      = business-case benefit - planned incremental operating cost.
* Measured benefit    = realised + validated benefit.
* Realised value      = realised benefit (financial or operational evidence) - actual incremental operating cost.
* Validated value     = benefit confirmed by the business owner but not yet evidenced in actuals.
* Hypothetical value  = expected value - realised value - validated value (business-case assumptions not yet evidenced).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import settings
from src.finance import formulas as F
from src.finance.repository import AS_OF, Repository
from src.synthetic.catalog import COMPANY, FY_MONTHS, QUARTERS

BENEFIT_TYPES = {"revenue": "Revenue uplift", "cost_savings": "Cost savings", "productivity": "Productivity value", "risk": "Risk-related value"}
COST_GROUPS = ["Infrastructure", "Software", "People", "Cloud", "Services", "Other"]

# At-risk rules (derived, never hard-coded per initiative). Red on any one; amber on any one.
RISK_RULES = {
    "realisation": ("Benefit realisation below plan", 0.50, 0.70),
    "budget": ("Spend above budget", 0.10, 0.05),
    "schedule": ("Go-live later than plan (months)", 3, 1),
    "adoption": ("Active adoption below target", 0.60, 0.85),
}


@dataclass
class Evidence:
    evidence_id: str
    label: str
    value: float | None
    unit: str
    formula: str
    components: list[dict] = field(default_factory=list)
    datasets: list[dict] = field(default_factory=list)
    query: str | None = None
    assumptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    data_label: str = "SYNTHETIC"

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["engine_version"] = settings.ENGINE_VERSION
        d["as_of"] = AS_OF
        return d


def _ds(table: str, rows: int, filt: str = "") -> dict:
    return {"table": table, "rows": int(rows), "filter": filt}


class PortfolioEngine:
    def __init__(self, repo: Repository | None = None):
        self.repo = repo or Repository()
        self.evidence: dict[str, Evidence] = {}
        self._table: pd.DataFrame | None = None

    # ------------------------------------------------------------------ building blocks
    def _benefit_lines(self) -> pd.DataFrame:
        bm = self.repo["benefit_monthly"]
        agg = bm.groupby("benefit_id")[["business_case_value", "measured_value", "realised_value", "validated_value"]].sum()
        lines = self.repo["benefits"].set_index("benefit_id").drop(columns=["business_case_value"]).join(agg, how="left").fillna(
            {"business_case_value": 0, "measured_value": 0, "realised_value": 0, "validated_value": 0})
        lines["hypothetical_value"] = (lines.business_case_value - lines.measured_value).clip(lower=0)
        return lines.reset_index()

    def initiative_table(self) -> pd.DataFrame:
        if self._table is not None:
            return self._table
        r = self.repo
        ini = r.initiatives.copy().set_index("initiative_id")
        pc = r.programme_costs
        ini["actual_spend"] = pc.groupby("initiative_id").amount.sum()
        ini["cloud_consumption"] = pc[pc.cost_category == "cloud"].groupby("initiative_id").amount.sum()
        ini["infrastructure_cost"] = pc[pc.cost_group == "Infrastructure"].groupby("initiative_id").amount.sum()
        ini["incremental_opex_actual"] = r.incremental_opex.groupby("initiative_id").amount.sum()
        fc = r["forecasts"]
        latest = fc[(fc.horizon == "FY2026") & (fc.forecast_version == "FY26 Q3 re-forecast")]
        ini["forecast_spend"] = latest.set_index("initiative_id").amount
        lines = self._benefit_lines()
        g = lines.groupby("initiative_id")
        ini["business_case_benefit"] = g.business_case_value.sum()
        ini["measured_benefit"] = g.measured_value.sum()
        ini["realised_benefit"] = g.realised_value.sum()
        ini["validated_value"] = g.validated_value.sum()
        ini["owner_forecast_benefit"] = g.owner_forecast_value.sum()
        for t in BENEFIT_TYPES:
            ini[f"expected_{t}"] = lines[lines.benefit_type == t].groupby("initiative_id").business_case_value.sum()
            ini[f"realised_{t}"] = lines[lines.benefit_type == t].groupby("initiative_id").realised_value.sum()
        ini = ini.fillna(0.0)
        ini["investment"] = ini.actual_spend
        ini["expected_value"] = ini.business_case_benefit - ini.incremental_opex_plan
        ini["realised_value"] = ini.realised_benefit - ini.incremental_opex_actual
        ini["hypothetical_value"] = ini.expected_value - ini.realised_value - ini.validated_value
        ini["budget_variance"] = ini.actual_spend - ini.budget
        ini["budget_variance_pct"] = ini.budget_variance / ini.budget
        ini["forecast_variance"] = ini.actual_spend - ini.forecast_spend
        ini["forecast_variance_pct"] = ini.forecast_variance / ini.forecast_spend
        ini["realised_roi"] = [F.roi(v, i) for v, i in zip(ini.realised_value, ini.investment)]
        ini["expected_roi"] = [F.roi(v, i) for v, i in zip(ini.expected_value, ini.investment)]
        ini["benefit_realisation"] = [F.benefit_realisation(a, b) for a, b in zip(ini.realised_value, ini.expected_value)]
        use = r["ai_usage"]
        last = use[use.month == FY_MONTHS[-1]].set_index("initiative_id")
        ini["active_users"] = last.active_users
        ini["adoption_rate"] = last.adoption_rate
        ini["adoption_vs_target"] = ini.adoption_rate / ini.adoption_target
        ini["schedule_slip_months"] = [
            (pd.Timestamp(a).year - pd.Timestamp(p).year) * 12 + pd.Timestamp(a).month - pd.Timestamp(p).month
            for a, p in zip(ini.actual_go_live, ini.planned_go_live)]
        risks = r["risks"]
        open_r = risks[risks.status != "Closed"]
        ini["open_risks"] = open_r.groupby("initiative_id").risk_id.count()
        ini["risk_exposure"] = (open_r.financial_impact * open_r.probability).groupby(open_r.initiative_id).sum()
        ini = ini.fillna({"open_risks": 0, "risk_exposure": 0.0, "active_users": 0, "adoption_rate": 0.0})
        life = self.lifecycle()
        ini = ini.join(life.set_index("initiative_id"))
        from src.finance.confidence import ConfidenceEngine

        conf = ConfidenceEngine(self).by_initiative()
        ini["confidence"] = conf
        ini["confidence_band"] = [ConfidenceEngine.band(c) for c in ini.confidence]
        flags = [self._flags(row) for _, row in ini.iterrows()]
        ini["risk_flags"] = flags
        ini["rag"] = ["Red" if any(f["level"] == "Red" for f in fl) else "Amber" if fl else "Green" for fl in flags]
        ini["at_risk"] = ini.rag == "Red"
        bus = r["business_units"].set_index("bu_id").name
        ini["business_unit"] = ini.bu_id.map(bus)
        self._table = ini.reset_index()
        return self._table

    @staticmethod
    def _flags(row) -> list[dict]:
        out = []
        checks = [
            ("realisation", row.benefit_realisation, lambda v, red, amb: v < red, lambda v, red, amb: v < amb, "{:.0%} of expected value realised"),
            ("budget", row.budget_variance_pct, lambda v, red, amb: v > red, lambda v, red, amb: v > amb, "{:+.0%} vs budget"),
            ("schedule", row.schedule_slip_months, lambda v, red, amb: v >= red, lambda v, red, amb: v >= amb, "{:.0f} month(s) late"),
            ("adoption", row.adoption_vs_target, lambda v, red, amb: v < red, lambda v, red, amb: v < amb, "{:.0%} of target adoption"),
        ]
        for key, v, is_red, is_amber, fmt in checks:
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            name, red, amb = RISK_RULES[key]
            level = "Red" if is_red(v, red, amb) else "Amber" if is_amber(v, red, amb) else None
            if level:
                out.append({"rule": key, "level": level, "label": name, "detail": fmt.format(v)})
        return out

    # ------------------------------------------------------------------ lifecycle (NPV / IRR / payback)
    def lifecycle(self) -> pd.DataFrame:
        """FY2026 actuals plus a two-year outlook built from documented planning assumptions (A-30..A-32).

        Outlook benefit  = FY26-Q4 measured monthly run-rate x 12 x persistence (A-31)
        Outlook cost     = FY26 programme spend x run-cost share (A-32) + annualised incremental opex
        """
        r = self.repo
        rate, persist, run_share = r.assumption("A-30"), r.assumption("A-31"), r.assumption("A-32")
        bm, pc, ox = r["benefit_monthly"], r.programme_costs, r.incremental_opex
        rows = []
        for iid in r.initiatives.initiative_id:
            spend = pc[pc.initiative_id == iid].groupby("month").amount.sum().reindex(FY_MONTHS, fill_value=0.0)
            opex = ox[ox.initiative_id == iid].groupby("month").amount.sum().reindex(FY_MONTHS, fill_value=0.0)
            b = bm[bm.initiative_id == iid].groupby("month")
            realised = b.realised_value.sum().reindex(FY_MONTHS, fill_value=0.0)
            measured = b.measured_value.sum().reindex(FY_MONTHS, fill_value=0.0)
            monthly = list(realised - spend - opex)
            run_rate = measured.iloc[-3:].mean()
            opex_rate = opex.iloc[-3:].mean()
            out_month = run_rate * persist - spend.sum() * run_share / 12 - opex_rate
            cfs_monthly = monthly + [out_month] * 24
            annual = [sum(monthly), out_month * 12, out_month * 12]
            rows.append({"initiative_id": iid, "npv_3yr": F.npv(rate, annual), "irr_3yr": F.irr(annual),
                         "payback_months": F.payback_months(cfs_monthly), "outlook_annual_net": out_month * 12})
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ portfolio KPIs
    def kpis(self) -> dict:
        t = self.initiative_table()
        r = self.repo
        inv, exp_v, real_v, val_v = t.investment.sum(), t.expected_value.sum(), t.realised_value.sum(), t.validated_value.sum()
        hyp_v = exp_v - real_v - val_v
        q = self.quarterly()
        q3, q4 = q.iloc[-2], q.iloc[-1]
        cost_growth = (q4.investment - q3.investment) / q3.investment
        infra = r["infrastructure_usage"]
        util = self._utilisation(infra[infra.quarter == "FY26-Q4"])
        k = {
            "total_investment": inv, "budget": t.budget.sum(), "realised_value": real_v, "expected_value": exp_v,
            "validated_value": val_v, "hypothetical_value": hyp_v, "net_value": F.net_value(real_v, inv),
            "expected_net_value": F.net_value(exp_v, inv), "realised_roi": F.roi(real_v, inv), "expected_roi": F.roi(exp_v, inv),
            "benefit_realisation": F.benefit_realisation(real_v, exp_v), "value_per_dollar": F.value_per_dollar(real_v, inv),
            "ai_cost_growth_qoq": cost_growth, "initiatives": int(len(t)), "at_risk": int(t.at_risk.sum()),
            "watch": int((t.rag == "Amber").sum()), "utilisation_q4": util, "budget_variance_pct": (inv - t.budget.sum()) / t.budget.sum(),
            "npv_3yr": t.npv_3yr.sum(), "as_of": AS_OF, "period": "FY2026 (Sep 2025 - Aug 2026)",
        }
        n_ct, n_bm = len(r.programme_costs), len(r["benefit_monthly"])
        E = self._reg
        E(Evidence("kpi.total_investment", "Total AI investment", inv, "USD", "Sum of programme spend, FY2026",
                   [{"label": g, "value": float(r.programme_costs[r.programme_costs.cost_group == g].amount.sum()), "evidence_id": f"waterfall.cost.{g}"} for g in COST_GROUPS],
                   [_ds("cost_transactions", n_ct, "cost_type = 'programme'")],
                   "SELECT SUM(amount) FROM cost_transactions WHERE cost_type = 'programme'"))
        E(Evidence("kpi.expected_value", "Expected AI value", exp_v, "USD", "Business-case benefit - planned incremental operating cost",
                   [{"label": BENEFIT_TYPES[b], "value": float(t[f"expected_{b}"].sum()), "evidence_id": f"waterfall.benefit.{b}"} for b in BENEFIT_TYPES]
                   + [{"label": "Incremental operating cost (plan)", "value": -float(t.incremental_opex_plan.sum())}],
                   [_ds("benefit_monthly", n_bm), _ds("ai_initiatives", len(t)), _ds("assumptions", len(r["assumptions"]))],
                   "SELECT SUM(business_case_value) FROM benefit_monthly; SELECT SUM(incremental_opex_plan) FROM ai_initiatives",
                   sorted({a for s in r["benefits"].assumption_ids.dropna() for a in s.split(",")}),
                   ["Expected value is the approved FY2026 business case; it is an assumption-based target, not an actual."]))
        E(Evidence("kpi.realised_value", "Realised AI value", real_v, "USD", "Realised benefit - actual incremental operating cost",
                   [{"label": BENEFIT_TYPES[b], "value": float(t[f"realised_{b}"].sum())} for b in BENEFIT_TYPES]
                   + [{"label": "Incremental operating cost (actual)", "value": -float(t.incremental_opex_actual.sum())}],
                   [_ds("benefit_monthly", n_bm, "realised_value"), _ds("benefit_evidence", len(r["benefit_evidence"])),
                    _ds("cost_transactions", len(r.incremental_opex), "cost_type = 'incremental_opex'")],
                   "SELECT SUM(realised_value) FROM benefit_monthly; SELECT SUM(amount) FROM cost_transactions WHERE cost_type = 'incremental_opex'",
                   notes=["Realised = supported by financial (GL) or operational (telemetry) evidence."]))
        E(Evidence("kpi.realised_roi", "Realised ROI", k["realised_roi"], "ratio", F.FORMULAS["roi"],
                   [{"label": "Realised value", "value": real_v, "evidence_id": "kpi.realised_value"},
                    {"label": "Investment", "value": inv, "evidence_id": "kpi.total_investment"}],
                   notes=["In-year view: FY2026 value against FY2026 spend. See lifecycle NPV for the multi-year view."]))
        E(Evidence("kpi.expected_roi", "Expected ROI", k["expected_roi"], "ratio", F.FORMULAS["roi"],
                   [{"label": "Expected value", "value": exp_v, "evidence_id": "kpi.expected_value"},
                    {"label": "Investment", "value": inv, "evidence_id": "kpi.total_investment"}]))
        E(Evidence("kpi.benefit_realisation", "Benefit realisation", k["benefit_realisation"], "ratio", F.FORMULAS["benefit_realisation"],
                   [{"label": "Realised value", "value": real_v, "evidence_id": "kpi.realised_value"},
                    {"label": "Expected value", "value": exp_v, "evidence_id": "kpi.expected_value"}]))
        E(Evidence("kpi.net_value", "Net AI value (realised)", k["net_value"], "USD", F.FORMULAS["net_value"],
                   [{"label": "Realised value", "value": real_v, "evidence_id": "kpi.realised_value"},
                    {"label": "Investment", "value": -inv, "evidence_id": "kpi.total_investment"}]))
        E(Evidence("kpi.ai_cost_growth_qoq", "AI cost growth (Q4 vs Q3)", cost_growth, "ratio", "(Q4 spend - Q3 spend) / Q3 spend",
                   [{"label": "FY26-Q3 spend", "value": float(q3.investment)}, {"label": "FY26-Q4 spend", "value": float(q4.investment)}],
                   [_ds("cost_transactions", n_ct, "cost_type = 'programme'")],
                   "SELECT quarter, SUM(amount) FROM cost_transactions WHERE cost_type='programme' GROUP BY quarter"))
        E(Evidence("kpi.at_risk", "At-risk initiatives", k["at_risk"], "count",
                   "Initiatives with at least one red flag: " + "; ".join(f"{v[0]} (red {v[1]})" for v in RISK_RULES.values()),
                   [{"label": row["name"], "value": None, "evidence_id": f"initiative.{row.initiative_id}",
                     "detail": ", ".join(f["detail"] for f in row.risk_flags if f["level"] == "Red")} for _, row in t[t.at_risk].iterrows()],
                   [_ds("ai_initiatives", len(t)), _ds("ai_usage", len(r["ai_usage"])), _ds("budgets", len(r["budgets"]))]))
        E(Evidence("kpi.value_classification", "Realised vs validated vs hypothetical", exp_v, "USD",
                   "Expected value = Realised + Validated + Hypothetical",
                   [{"label": "Realised", "value": real_v, "evidence_id": "kpi.realised_value"},
                    {"label": "Validated (owner-confirmed, not yet in actuals)", "value": val_v},
                    {"label": "Hypothetical (business-case assumptions not yet evidenced)", "value": hyp_v}],
                   [_ds("benefit_monthly", n_bm), _ds("benefit_evidence", len(r["benefit_evidence"]))]))
        return k

    def _reg(self, e: Evidence) -> None:
        self.evidence[e.evidence_id] = e

    @staticmethod
    def _utilisation(df: pd.DataFrame) -> float | None:
        cap = df.gpu_hours_capacity.sum()
        return None if cap == 0 else float(df.gpu_hours_used.sum() / cap)

    # ------------------------------------------------------------------ value bridge
    def waterfall(self) -> dict:
        t, r = self.initiative_table(), self.repo
        pc = r.programme_costs
        steps = []
        for g in COST_GROUPS:
            amt = float(pc[pc.cost_group == g].amount.sum())
            by = pc[pc.cost_group == g].groupby("initiative_id").amount.sum().sort_values(ascending=False)
            steps.append({"id": f"waterfall.cost.{g}", "label": g, "kind": "investment", "value": -amt,
                          "drilldown": [{"initiative_id": i, "value": float(v)} for i, v in by.items()]})
            self._reg(Evidence(f"waterfall.cost.{g}", f"Investment: {g}", amt, "USD", f"Sum of programme spend in cost group '{g}'",
                               [{"label": c, "value": float(v)} for c, v in pc[pc.cost_group == g].groupby("cost_category").amount.sum().items()],
                               [_ds("cost_transactions", int((pc.cost_group == g).sum()), f"cost_group = '{g}'")],
                               f"SELECT cost_category, SUM(amount) FROM cost_transactions WHERE cost_type='programme' AND cost_group='{g}' GROUP BY cost_category"))
        for b, label in BENEFIT_TYPES.items():
            amt = float(t[f"realised_{b}"].sum())
            by = t.set_index("initiative_id")[f"realised_{b}"]
            by = by[by > 0].sort_values(ascending=False)
            steps.append({"id": f"waterfall.benefit.{b}", "label": label, "kind": "benefit", "value": amt,
                          "expected": float(t[f"expected_{b}"].sum()),
                          "drilldown": [{"initiative_id": i, "value": float(v)} for i, v in by.items()]})
            self._reg(Evidence(f"waterfall.benefit.{b}", f"Realised {label.lower()}", amt, "USD", f"Sum of realised benefit where benefit_type = '{b}'",
                               [{"label": i, "value": float(v), "evidence_id": f"initiative.{i}"} for i, v in by.items()],
                               [_ds("benefit_monthly", int((r['benefit_monthly'].benefit_type == b).sum()), f"benefit_type = '{b}'")],
                               f"SELECT initiative_id, SUM(realised_value) FROM benefit_monthly WHERE benefit_type='{b}' GROUP BY initiative_id",
                               notes=[f"Business case for this benefit type: {t[f'expected_{b}'].sum():,.0f} USD"]))
        opex = float(t.incremental_opex_actual.sum())
        steps.append({"id": "waterfall.opex", "label": "Incremental operating costs", "kind": "opex", "value": -opex,
                      "drilldown": [{"initiative_id": i, "value": float(v)} for i, v in
                                    t.set_index("initiative_id").incremental_opex_actual.sort_values(ascending=False).items() if v > 0]})
        net = sum(s["value"] for s in steps)
        steps.append({"id": "kpi.net_value", "label": "Net AI value", "kind": "total", "value": net})
        return {"steps": steps, "net_value": net, "basis": "Realised FY2026 value against FY2026 investment"}

    # ------------------------------------------------------------------ time series
    def quarterly(self) -> pd.DataFrame:
        r = self.repo
        pc, ox, bm, iu = r.programme_costs, r.incremental_opex, r["benefit_monthly"], r["infrastructure_usage"]
        rows = []
        for q in QUARTERS:
            inv = pc[pc.quarter == q].amount.sum()
            val = bm[bm.quarter == q].realised_value.sum() - ox[ox.quarter == q].amount.sum()
            rows.append({"quarter": q, "investment": inv, "realised_value": val,
                         "measured_value": bm[bm.quarter == q].measured_value.sum() - ox[ox.quarter == q].amount.sum(),
                         "business_case_value": bm[bm.quarter == q].business_case_value.sum(),
                         "validated_value": bm[bm.quarter == q].validated_value.sum(),
                         "infrastructure_cost": pc[(pc.quarter == q) & (pc.cost_group == "Infrastructure")].amount.sum(),
                         "cloud_cost": pc[(pc.quarter == q) & (pc.cost_group == "Cloud")].amount.sum(),
                         "utilisation": self._utilisation(iu[iu.quarter == q]), "roi": F.roi(val, inv) if inv else None})
        return pd.DataFrame(rows)

    def monthly(self) -> pd.DataFrame:
        r = self.repo
        pc, bm, iu, bud = r.programme_costs, r["benefit_monthly"], r["infrastructure_usage"], r["budgets"]
        df = pd.DataFrame({"month": FY_MONTHS})
        df["actual"] = df.month.map(pc.groupby("month").amount.sum()).fillna(0)
        df["budget"] = df.month.map(bud.groupby("month").budget_amount.sum()).fillna(0)
        df["realised_benefit"] = df.month.map(bm.groupby("month").realised_value.sum()).fillna(0)
        df["business_case_benefit"] = df.month.map(bm.groupby("month").business_case_value.sum()).fillna(0)
        df["validated_benefit"] = df.month.map(bm.groupby("month").validated_value.sum()).fillna(0)
        g = iu.groupby("month")[["gpu_hours_used", "gpu_hours_capacity"]].sum()
        df["utilisation"] = df.month.map(g.gpu_hours_used / g.gpu_hours_capacity)
        return df

    # ------------------------------------------------------------------ ROI movement
    def roi_movement(self, q_from: str = "FY26-Q3", q_to: str = "FY26-Q4") -> dict:
        """Exact decomposition of the change in quarterly ROI.

        ROI = V/C - 1, so dROI = V2/C2 - V1/C1 = (V2 - V1)/C2  [value effect]  +  V1*(1/C2 - 1/C1)  [cost effect].
        Per initiative i: contribution_i = dV_i / C2 - V1 * dC_i / (C1 * C2). Contributions sum to dROI exactly.
        """
        r = self.repo
        pc, ox, bm, iu = r.programme_costs, r.incremental_opex, r["benefit_monthly"], r["infrastructure_usage"]

        def per_ini(q):
            c = pc[pc.quarter == q].groupby("initiative_id").amount.sum()
            v = bm[bm.quarter == q].groupby("initiative_id").realised_value.sum().sub(
                ox[ox.quarter == q].groupby("initiative_id").amount.sum(), fill_value=0)
            return c.reindex(r.initiatives.initiative_id, fill_value=0), v.reindex(r.initiatives.initiative_id, fill_value=0)

        c1, v1 = per_ini(q_from)
        c2, v2 = per_ini(q_to)
        C1, C2, V1, V2 = c1.sum(), c2.sum(), v1.sum(), v2.sum()
        roi1, roi2 = F.roi(V1, C1), F.roi(V2, C2)
        contrib = (v2 - v1) / C2 - V1 * (c2 - c1) / (C1 * C2)
        names = r.initiatives.set_index("initiative_id").name
        rows = pd.DataFrame({"initiative_id": contrib.index, "name": names.reindex(contrib.index).values,
                             "contribution_pp": contrib.values * 100, "value_change": (v2 - v1).values, "cost_change": (c2 - c1).values})
        rows = rows.sort_values("contribution_pp")
        by_group = {}
        for g in COST_GROUPS:
            a = pc[(pc.quarter == q_from) & (pc.cost_group == g)].amount.sum()
            b = pc[(pc.quarter == q_to) & (pc.cost_group == g)].amount.sum()
            by_group[g] = {"from": a, "to": b, "change_pct": (b - a) / a if a else None}
        u1, u2 = self._utilisation(iu[iu.quarter == q_from]), self._utilisation(iu[iu.quarter == q_to])
        cap1 = iu[iu.quarter == q_from].gpu_hours_capacity.sum()
        cap2 = iu[iu.quarter == q_to].gpu_hours_capacity.sum()
        # value-per-unit revisions: lines whose measured value per active user fell by > 20% quarter on quarter
        revisions = []
        use = r["ai_usage"]
        for bid, grp in bm.groupby("benefit_id"):
            iid = grp.initiative_id.iloc[0]
            u = use[use.initiative_id == iid]
            a1 = u[u.quarter == q_from].active_users.sum()
            a2 = u[u.quarter == q_to].active_users.sum()
            m1 = grp[grp.quarter == q_from].measured_value.sum()
            m2 = grp[grp.quarter == q_to].measured_value.sum()
            if a1 and a2 and m1 > 0:
                chg = (m2 / a2) / (m1 / a1) - 1
                if chg < -0.2:
                    revisions.append({"benefit_id": bid, "initiative_id": iid, "name": names[iid], "value_per_user_change": chg})
        lag = {"from": bm[bm.quarter == q_from].validated_value.sum(), "to": bm[bm.quarter == q_to].validated_value.sum()}
        delayed = self.initiative_table()
        delayed = delayed[delayed.schedule_slip_months > 0][["initiative_id", "name", "schedule_slip_months", "actual_go_live"]]
        result = {
            "from": q_from, "to": q_to, "roi_from": roi1, "roi_to": roi2, "change_pp": (roi2 - roi1) * 100,
            "value_effect_pp": (V2 - V1) / C2 * 100, "cost_effect_pp": (V1 / C2 - V1 / C1) * 100,
            "cost_from": C1, "cost_to": C2, "value_from": V1, "value_to": V2,
            "cost_groups": by_group, "utilisation_from": u1, "utilisation_to": u2,
            "capacity_change_pct": (cap2 - cap1) / cap1 if cap1 else None,
            "initiatives": rows.to_dict("records"), "value_per_unit_revisions": revisions,
            "validated_pending": lag, "delayed_initiatives": delayed.to_dict("records"),
        }
        self._reg(Evidence("analysis.roi_movement", f"ROI movement {q_from} to {q_to}", result["change_pp"], "pp",
                           "dROI = (V2-V1)/C2 [value effect] + V1(1/C2-1/C1) [cost effect]; contributions per initiative sum to dROI",
                           [{"label": x["name"], "value": x["contribution_pp"], "evidence_id": f"initiative.{x['initiative_id']}"} for x in rows.to_dict("records")],
                           [_ds("cost_transactions", len(pc)), _ds("benefit_monthly", len(bm)), _ds("infrastructure_usage", len(iu))],
                           "SELECT quarter, initiative_id, SUM(amount) FROM cost_transactions GROUP BY 1,2; SELECT quarter, initiative_id, SUM(realised_value) FROM benefit_monthly GROUP BY 1,2"))
        return result

    # ------------------------------------------------------------------ initiative drill-down
    def initiative_detail(self, initiative_id: str) -> dict | None:
        t = self.initiative_table()
        row = t[t.initiative_id == initiative_id]
        if row.empty:
            return None
        row = row.iloc[0]
        r = self.repo
        pc = r.programme_costs[r.programme_costs.initiative_id == initiative_id]
        bud = r["budgets"][r["budgets"].initiative_id == initiative_id]
        cats = pd.DataFrame({"actual": pc.groupby("cost_category").amount.sum(), "budget": bud.groupby("cost_category").budget_amount.sum()}).fillna(0)
        cats["variance"] = cats.actual - cats.budget
        lines = self._benefit_lines()
        lines = lines[lines.initiative_id == initiative_id]
        use = r["ai_usage"][r["ai_usage"].initiative_id == initiative_id]
        detail = {
            "initiative": _clean(row.to_dict()),
            "cost_by_category": [{"category": c, **{k: float(v) for k, v in x.items()}} for c, x in cats.sort_values("actual", ascending=False).iterrows()],
            "monthly": [{"month": m, "spend": float(pc[pc.month == m].amount.sum()), "budget": float(bud[bud.month == m].budget_amount.sum()),
                         "realised": float(r["benefit_monthly"][(r["benefit_monthly"].initiative_id == initiative_id) & (r["benefit_monthly"].month == m)].realised_value.sum()),
                         "business_case": float(r["benefit_monthly"][(r["benefit_monthly"].initiative_id == initiative_id) & (r["benefit_monthly"].month == m)].business_case_value.sum())}
                        for m in FY_MONTHS],
            "benefit_lines": [_clean(x) for x in lines.to_dict("records")],
            "usage": [_clean(x) for x in use.to_dict("records")],
            "milestones": [_clean(x) for x in r["milestones"][r["milestones"].initiative_id == initiative_id].to_dict("records")],
            "risks": [_clean(x) for x in r["risks"][r["risks"].initiative_id == initiative_id].to_dict("records")],
            "funding": [_clean(x) for x in r["investment_transactions"][r["investment_transactions"].initiative_id == initiative_id].to_dict("records")],
        }
        self._reg(Evidence(f"initiative.{initiative_id}", row["name"], float(row.realised_value), "USD",
                           "Realised value = realised benefit - incremental opex; ROI = (realised value - investment) / investment",
                           [{"label": "Investment (actual spend)", "value": float(row.investment)},
                            {"label": "Budget", "value": float(row.budget)},
                            {"label": "Expected value", "value": float(row.expected_value)},
                            {"label": "Realised value", "value": float(row.realised_value)},
                            {"label": "Validated value", "value": float(row.validated_value)},
                            {"label": "Hypothetical value", "value": float(row.hypothetical_value)}],
                           [_ds("cost_transactions", len(pc), f"initiative_id = '{initiative_id}'"),
                            _ds("benefit_monthly", int((r['benefit_monthly'].initiative_id == initiative_id).sum()), f"initiative_id = '{initiative_id}'"),
                            _ds("ai_usage", len(use), f"initiative_id = '{initiative_id}'")],
                           f"SELECT * FROM ai_initiatives WHERE initiative_id = '{initiative_id}'",
                           sorted({a for s in lines.assumption_ids.dropna() for a in s.split(",")})))
        return detail

    def get_evidence(self, evidence_id: str) -> dict | None:
        if evidence_id not in self.evidence:
            self.kpis()
            self.waterfall()
            self.roi_movement()
            if evidence_id.startswith("initiative."):
                self.initiative_detail(evidence_id.split(".", 1)[1])
            if evidence_id.startswith(("benefit.", "confidence.")):
                from src.finance.benefits import BenefitsEngine

                BenefitsEngine(self).register_evidence()
            if evidence_id.startswith(("cost.", "unit.")):
                from src.finance.costs import CostEngine

                CostEngine(self).register_evidence()
        e = self.evidence.get(evidence_id)
        return e.to_dict() if e else None


def _clean(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, (np.floating, float)):
            out[k] = None if np.isnan(v) else float(v)
        elif isinstance(v, np.integer):
            out[k] = int(v)
        elif isinstance(v, np.bool_):
            out[k] = bool(v)
        else:
            out[k] = v
    return out


def records(df: pd.DataFrame) -> list[dict]:
    return [_clean(x) for x in df.to_dict("records")]


COMPANY_PROFILE = COMPANY
