"""Financial data repository - the single source of truth the calculation engine reads from.

Backed by SQLite via SQLAlchemy (swap the URL for PostgreSQL in an enterprise deployment). The committed
``financial_facts.csv`` is the portable, reviewable artefact; the database is rebuilt from it on demand.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine, text

from src import settings
from src.financial_model.schema import FinancialFact


class DataUnavailable(LookupError):
    """Raised when a required fact is not present in the public filings loaded into the model."""


class DataConflict(ValueError):
    """Raised when sources disagree and the fact is blocked for manual review."""


def build_database(csv_path=settings.FINANCIAL_FACTS_CSV, db_path=settings.DB_PATH) -> None:
    df = pd.read_csv(csv_path, dtype={"dimension_member": str}).fillna({"dimension_member": "", "dimension_type": "", "dimension_label": ""})
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        df.to_sql("financial_facts", conn, if_exists="replace", index=False)
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_fact_key ON financial_facts(fact_key)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_metric ON financial_facts(metric_id, fiscal_year)"))
    engine.dispose()


class FinancialRepository:
    def __init__(self, db_path=settings.DB_PATH, csv_path=settings.FINANCIAL_FACTS_CSV):
        if not db_path.exists() or (csv_path.exists() and csv_path.stat().st_mtime > db_path.stat().st_mtime):
            build_database(csv_path, db_path)
        self.engine = create_engine(f"sqlite:///{db_path}")
        with self.engine.connect() as conn:
            self.df = pd.read_sql(text("SELECT * FROM financial_facts"), conn)
        self.df["dimension_member"] = self.df["dimension_member"].fillna("")
        for c in ["dimension_type", "dimension_label", "row_label", "column_label", "source_table", "xbrl_concept", "xbrl_fact_id", "currency"]:
            self.df[c] = self.df[c].fillna("")
        self._index = {k: r for k, r in zip(self.df["fact_key"], self.df.to_dict("records"))}

    # ---- lookups -----------------------------------------------------------------------------------------
    def query(self, sql: str, **params) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def get(self, metric_id: str, fiscal_year: int, member: str = "", allow_conflict: bool = False) -> FinancialFact:
        rec = self._index.get(f"{metric_id}|FY{fiscal_year}|{member}")
        if rec is None:
            raise DataUnavailable(f"{metric_id} FY{fiscal_year} {member}".strip())
        rec = {k: (None if (isinstance(v, float) and pd.isna(v) and k == "table_index") else v) for k, v in rec.items()}
        fact = FinancialFact(**rec)
        if fact.consistency == "conflict" and not allow_conflict:
            raise DataConflict(f"{fact.fact_key}: the available sources contain differing values - manual review required")
        return fact

    def has(self, metric_id: str, fiscal_year: int, member: str = "") -> bool:
        return f"{metric_id}|FY{fiscal_year}|{member}" in self._index

    def years(self, metric_id: str = "revenue", member: str = "") -> list[int]:
        d = self.df[(self.df.metric_id == metric_id) & (self.df.dimension_member == member)]
        return sorted(int(y) for y in d.fiscal_year.unique())

    def members(self, metric_id: str) -> pd.DataFrame:
        d = self.df[self.df.metric_id == metric_id][["dimension_member", "dimension_label"]].drop_duplicates()
        return d.reset_index(drop=True)

    def statement(self, statement: str, years: list[int] | None = None) -> pd.DataFrame:
        d = self.df[(self.df.statement == statement) & (self.df.dimension_member == "")]
        if years:
            d = d[d.fiscal_year.isin(years)]
        return d.pivot_table(index=["metric_id", "metric_label"], columns="fiscal_year", values="value", aggfunc="first")

    @property
    def latest_year(self) -> int:
        return max(self.years("revenue"))


@lru_cache(maxsize=1)
def get_repository() -> FinancialRepository:
    return FinancialRepository()
