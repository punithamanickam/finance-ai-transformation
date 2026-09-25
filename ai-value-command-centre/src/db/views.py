"""Materialised semantic views used by the natural-language query layer.

They are computed by the deterministic engines (so the SQL a user sees returns exactly the numbers on screen) and
rebuilt whenever the database is rebuilt.
"""
from __future__ import annotations

import json

import pandas as pd
from sqlalchemy.engine import Engine

from src.finance import repository


def materialise(engine: Engine) -> dict[str, int]:
    from src.finance.benefits import BenefitsEngine
    from src.finance.portfolio import PortfolioEngine

    repository.reload()
    p = PortfolioEngine()
    t = p.initiative_table().drop(columns=["risk_flags"]).copy()
    t["risk_flags"] = [json.dumps(f) for f in p.initiative_table().risk_flags]
    b = BenefitsEngine(p)
    lines = pd.DataFrame(b.realisation_table())
    dep = pd.DataFrame(b.assumption_dependency())[["benefit_id", "assumption_share"]]
    lines = lines.merge(dep, on="benefit_id", how="left")
    lines["bu_id"] = lines.initiative_id.map(t.set_index("initiative_id").bu_id)
    risks = p.repo["risks"].copy()
    risks["exposure"] = risks.financial_impact * risks.probability
    risks["initiative_name"] = risks.initiative_id.map(t.set_index("initiative_id")["name"])
    risks["bu_id"] = risks.initiative_id.map(t.set_index("initiative_id").bu_id)
    pc, bud = p.repo.programme_costs, p.repo["budgets"]
    costs = pd.DataFrame({"actual": pc.groupby(["initiative_id", "cost_category", "cost_group"]).amount.sum(),
                          "budget": bud.groupby(["initiative_id", "cost_category", "cost_group"]).budget_amount.sum()}).fillna(0).reset_index()
    costs["variance"] = costs.actual - costs.budget
    costs["initiative_name"] = costs.initiative_id.map(t.set_index("initiative_id")["name"])
    costs["bu_id"] = costs.initiative_id.map(t.set_index("initiative_id").bu_id)
    out = {"ai_initiative_metrics": t, "benefit_line_metrics": lines, "risk_register": risks.drop(columns=["data_label"], errors="ignore"),
           "cost_by_category": costs}
    with engine.begin() as conn:
        for name, df in out.items():
            df = df.copy()
            df["data_label"] = "SYNTHETIC"
            df.to_sql(name, conn, if_exists="replace", index=False)
    return {k: len(v) for k, v in out.items()}
