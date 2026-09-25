"""Cost intelligence and unit economics, computed from cost transactions, budgets, usage and company reference data.

Forecast convention (same rule the synthetic Q3 re-forecast uses, documented so category forecasts reconcile to it):
    full-year forecast = actual Q1-Q3 + budget Q4 x (0.5 + 0.5 x actual Q1-Q3 / budget Q1-Q3)
"""
from __future__ import annotations

import pandas as pd

from src.finance import formulas as F
from src.finance.portfolio import Evidence, _ds, records
from src.synthetic.catalog import COMPANY, FY_MONTHS

CATEGORY_LABELS = {"compute": "Compute", "gpu": "GPU", "cloud": "Cloud", "storage": "Storage", "networking": "Networking",
                   "software": "Software", "saas": "SaaS", "vendors": "Vendors", "consulting": "Consulting",
                   "employees": "Employees", "training": "Training", "data": "Data"}


class CostEngine:
    def __init__(self, portfolio):
        self.p = portfolio
        self.repo = portfolio.repo

    def by_category(self) -> list[dict]:
        pc, bud = self.repo.programme_costs, self.repo["budgets"]
        first3 = FY_MONTHS[:9]
        rows = []
        for c, label in CATEGORY_LABELS.items():
            a = pc[pc.cost_category == c]
            b = bud[bud.cost_category == c]
            actual, budget = a.amount.sum(), b.budget_amount.sum()
            a9, b9 = a[a.month.isin(first3)].amount.sum(), b[b.month.isin(first3)].budget_amount.sum()
            b_q4 = b[~b.month.isin(first3)].budget_amount.sum()
            forecast = a9 + b_q4 * (0.5 + 0.5 * (a9 / b9 if b9 else 1.0))
            q = a.groupby("quarter").amount.sum()
            trend = (q.get("FY26-Q4", 0) - q.get("FY26-Q3", 0)) / q.get("FY26-Q3", 1) if q.get("FY26-Q3", 0) else None
            var, var_pct = F.budget_variance(actual, budget)
            rows.append({"category": c, "label": label, "actual": actual, "budget": budget, "forecast": forecast,
                         "variance": var, "variance_pct": var_pct, "forecast_variance": actual - forecast,
                         "qoq_trend": trend, "monthly": [float(a[a.month == m].amount.sum()) for m in FY_MONTHS]})
        return sorted(rows, key=lambda r: -r["actual"])

    def by_business_unit(self) -> list[dict]:
        t = self.p.initiative_table()
        g = t.groupby("business_unit").agg(investment=("investment", "sum"), budget=("budget", "sum"),
                                           realised_value=("realised_value", "sum"), expected_value=("expected_value", "sum"),
                                           initiatives=("initiative_id", "count")).reset_index()
        g["realised_roi"] = [F.roi(v, i) for v, i in zip(g.realised_value, g.investment)]
        return records(g.sort_values("investment", ascending=False))

    def by_vendor(self) -> list[dict]:
        pc = self.repo.programme_costs
        v = self.repo["vendors"].set_index("vendor_id").name
        g = pc.assign(vendor=pc.vendor_id.map(v).fillna("Internal staff")).groupby("vendor").amount.sum().sort_values(ascending=False)
        return [{"vendor": k, "amount": float(x)} for k, x in g.items()]

    def cost_growth_drivers(self) -> dict:
        pc = self.repo.programme_costs
        q3, q4 = pc[pc.quarter == "FY26-Q3"], pc[pc.quarter == "FY26-Q4"]
        total3, total4 = q3.amount.sum(), q4.amount.sum()
        cat = pd.DataFrame({"q3": q3.groupby("cost_category").amount.sum(), "q4": q4.groupby("cost_category").amount.sum()}).fillna(0)
        cat["change"] = cat.q4 - cat.q3
        ini = pd.DataFrame({"q3": q3.groupby("initiative_id").amount.sum(), "q4": q4.groupby("initiative_id").amount.sum()}).fillna(0)
        ini["change"] = ini.q4 - ini.q3
        names = self.repo.initiatives.set_index("initiative_id").name
        top_cells = (q4.groupby(["initiative_id", "cost_category"]).amount.sum()
                     .sub(q3.groupby(["initiative_id", "cost_category"]).amount.sum(), fill_value=0).sort_values(ascending=False).head(6))
        return {"q3": total3, "q4": total4, "growth": (total4 - total3) / total3 if total3 else None,
                "by_category": [{"category": c, "label": CATEGORY_LABELS[c], "q3": float(x.q3), "q4": float(x.q4), "change": float(x.change),
                                 "change_pct": float(x.change / x.q3) if x.q3 else None} for c, x in cat.sort_values("change", ascending=False).iterrows()],
                "by_initiative": [{"initiative_id": i, "name": names[i], "change": float(x.change)} for i, x in ini.sort_values("change", ascending=False).iterrows()],
                "top_movements": [{"initiative_id": i, "name": names[i], "category": CATEGORY_LABELS[c], "change": float(v)} for (i, c), v in top_cells.items()]}

    def unit_economics(self) -> dict:
        t = self.p.initiative_table()
        use = self.repo["ai_usage"]
        pc = self.repo.programme_costs
        inv = t.investment.sum()
        total_cost = inv + t.incremental_opex_actual.sum()
        interactions, transactions = use.interactions.sum(), use.transactions.sum()
        rev = t.realised_revenue.sum()
        savings = t.realised_cost_savings.sum()
        employees = COMPANY["employees"] if not self.repo.bu_scope else int(
            self.repo["business_units"].set_index("bu_id").headcount.get(self.repo.bu_scope, 0))
        peak_active = use[use.month == FY_MONTHS[-1]].active_users.sum()
        iu = self.repo["infrastructure_usage"]
        m = {
            "ai_cost_per_employee": F.cost_per_outcome(total_cost, employees),
            "ai_cost_per_customer": F.cost_per_outcome(total_cost, COMPANY["customers"]) if not self.repo.bu_scope else None,
            "ai_cost_per_active_user": F.cost_per_outcome(total_cost, peak_active),
            "ai_cost_per_transaction": F.cost_per_outcome(total_cost, transactions),
            "ai_cost_per_interaction": F.cost_per_outcome(total_cost, interactions),
            "ai_cost_per_gpu_hour_used": F.cost_per_outcome(iu.infrastructure_cost.sum(), iu.gpu_hours_used.sum()),
            "ai_cost_per_dollar_revenue": F.cost_per_outcome(total_cost, rev) if rev else None,
            "ai_cost_per_dollar_savings": F.cost_per_outcome(total_cost, savings) if savings else None,
            "value_per_dollar_invested": F.value_per_dollar(t.realised_value.sum(), inv),
        }
        inputs = {"total_cost": total_cost, "investment": inv, "employees": employees, "customers": COMPANY["customers"],
                  "active_users": int(peak_active), "transactions": int(transactions), "interactions": int(interactions),
                  "realised_revenue_margin": rev, "realised_cost_savings": savings}
        per_ini = []
        for _, row in t.iterrows():
            u = use[use.initiative_id == row.initiative_id]
            cost = row.investment + row.incremental_opex_actual
            outcome = u.transactions.sum()
            per_ini.append({"initiative_id": row.initiative_id, "name": row["name"], "transaction_type": u.transaction_type.iloc[0] if len(u) else None,
                            "cost_per_transaction": F.cost_per_outcome(cost, outcome) if outcome else None,
                            "cost_per_active_user": F.cost_per_outcome(cost, row.active_users) if row.active_users else None,
                            "value_per_dollar": F.value_per_dollar(row.realised_value, row.investment),
                            "cost_per_dollar_value": F.cost_per_outcome(cost, row.realised_benefit) if row.realised_benefit > 0 else None})
        del pc
        return {"metrics": m, "inputs": inputs, "by_initiative": per_ini,
                "notes": ["Total cost = programme investment + incremental operating cost.",
                          "Revenue uplift is measured as incremental gross margin, so cost per $1 of revenue uses margin."]}

    def infrastructure(self) -> dict:
        iu = self.repo["infrastructure_usage"]
        clusters = []
        for cid, g in iu.groupby("cluster_id"):
            g = g.sort_values("month")
            clusters.append({"cluster_id": cid, "name": g.cluster_name.iloc[0], "platform": g.platform.iloc[0], "region": g.region.iloc[0],
                             "hpe_product_id": g.hpe_product_id.iloc[0], "gpus_now": int(g.gpus.iloc[-1]),
                             "utilisation_q3": float(g[g.quarter == "FY26-Q3"].gpu_hours_used.sum() / g[g.quarter == "FY26-Q3"].gpu_hours_capacity.sum()) if (g.quarter == "FY26-Q3").any() else None,
                             "utilisation_q4": float(g[g.quarter == "FY26-Q4"].gpu_hours_used.sum() / g[g.quarter == "FY26-Q4"].gpu_hours_capacity.sum()),
                             "cost_fy": float(g.infrastructure_cost.sum()), "cost_q4": float(g[g.quarter == "FY26-Q4"].infrastructure_cost.sum()),
                             "idle_gpu_hours_q4": float((g[g.quarter == "FY26-Q4"].gpu_hours_capacity - g[g.quarter == "FY26-Q4"].gpu_hours_used).sum()),
                             "monthly": records(g[["month", "gpus", "gpu_hours_capacity", "gpu_hours_used", "utilisation", "infrastructure_cost"]])})
        m = iu.groupby("month")[["gpu_hours_used", "gpu_hours_capacity", "infrastructure_cost"]].sum().reset_index()
        m["utilisation"] = m.gpu_hours_used / m.gpu_hours_capacity
        return {"clusters": clusters, "monthly": records(m)}

    def register_evidence(self) -> None:
        for c in self.by_category():
            self.p._reg(Evidence(f"cost.{c['category']}", f"{c['label']} cost", c["actual"], "USD", "Sum of programme spend; variance = actual - budget",
                                 [{"label": "Actual", "value": c["actual"]}, {"label": "Budget", "value": c["budget"]},
                                  {"label": "Forecast (Q3 rule)", "value": c["forecast"]}, {"label": "Variance", "value": c["variance"]}],
                                 [_ds("cost_transactions", int((self.repo.programme_costs.cost_category == c["category"]).sum()), f"cost_category = '{c['category']}'"),
                                  _ds("budgets", int((self.repo["budgets"].cost_category == c["category"]).sum()), f"cost_category = '{c['category']}'")],
                                 f"SELECT month, SUM(amount) FROM cost_transactions WHERE cost_type='programme' AND cost_category='{c['category']}' GROUP BY month"))
        u = self.unit_economics()
        for k, v in u["metrics"].items():
            self.p._reg(Evidence(f"unit.{k}", k.replace("_", " "), v, "USD" if "value_per" not in k else "ratio",
                                 "Cost / outcome volume (see inputs)", [{"label": a, "value": b} for a, b in u["inputs"].items()],
                                 [_ds("cost_transactions", len(self.repo["cost_transactions"])), _ds("ai_usage", len(self.repo["ai_usage"]))],
                                 notes=u["notes"]))
