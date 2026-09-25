"""Data access for the analytics engines: loads tables from the database once and applies role-based BU scope."""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from src.db.database import ensure_base_database, read_table
from src.synthetic.catalog import FY_MONTHS, QUARTERS

AS_OF = "2026-08-31"  # last closed month of the synthetic data
QUARTER_OF = {FY_MONTHS[i]: q for q, idx in QUARTERS.items() for i in idx}
SCOPED = ["ai_initiatives", "cost_transactions", "budgets", "forecasts", "benefits", "benefit_monthly", "ai_usage",
          "risks", "milestones", "investment_transactions"]


@lru_cache(maxsize=1)
def _load_all() -> dict[str, pd.DataFrame]:
    engine = ensure_base_database()
    names = SCOPED + ["benefit_evidence", "infrastructure_usage", "assumptions", "vendors", "business_units", "companies",
                      "financials", "cost_centres", "hpe_products", "hpe_sources", "hpe_financials"]
    out = {}
    for n in names:
        try:
            out[n] = read_table(n, engine)
        except Exception:
            out[n] = pd.DataFrame()
    for n in ("cost_transactions", "budgets", "benefit_monthly", "ai_usage", "infrastructure_usage"):
        out[n]["quarter"] = out[n]["month"].map(QUARTER_OF)
    return out


def reload() -> None:
    _load_all.cache_clear()


class Repository:
    """Read-only view of the data model, optionally restricted to one business unit."""

    def __init__(self, bu_scope: str | None = None):
        self.bu_scope = bu_scope
        data = _load_all()
        ini = data["ai_initiatives"]
        if bu_scope:
            ini = ini[ini.bu_id == bu_scope]
        ids = set(ini.initiative_id)
        self.t: dict[str, pd.DataFrame] = {}
        for name, df in data.items():
            if name in SCOPED and "initiative_id" in df.columns:
                df = df[df.initiative_id.isin(ids)]
            if name == "benefit_evidence" and not df.empty:
                df = df[df.benefit_id.str[:6].isin(ids)]
            self.t[name] = df.reset_index(drop=True)
        if bu_scope:
            clusters = set(ini.cluster_id)
            self.t["infrastructure_usage"] = self.t["infrastructure_usage"][self.t["infrastructure_usage"].cluster_id.isin(clusters)]
            self.t["financials"] = self.t["financials"][self.t["financials"].bu_id == bu_scope]

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.t[name]

    @property
    def initiatives(self) -> pd.DataFrame:
        return self.t["ai_initiatives"]

    @property
    def programme_costs(self) -> pd.DataFrame:
        c = self.t["cost_transactions"]
        return c[c.cost_type == "programme"]

    @property
    def incremental_opex(self) -> pd.DataFrame:
        c = self.t["cost_transactions"]
        return c[c.cost_type == "incremental_opex"]

    def assumption(self, assumption_id: str) -> float:
        a = self.t["assumptions"]
        return float(a.loc[a.assumption_id == assumption_id, "value"].iloc[0])
