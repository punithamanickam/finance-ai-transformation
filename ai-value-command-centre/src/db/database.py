"""Database build and access. `python -m src.db.database` rebuilds the database from committed CSVs and public sources."""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine, insert, text
from sqlalchemy.engine import Engine

from src import settings
from src.db import schema

DEMO_USERS = [
    # user_id, display name, role, BU scope
    ("cfo@meridian.example", "Group CFO", "CFO", None),
    ("fpa@meridian.example", "FP&A Lead", "FINANCE", None),
    ("bu.supplychain@meridian.example", "COO, Supply Chain & Manufacturing", "BU", "BU-SCM"),
    ("bu.sales@meridian.example", "CRO, Sales & Commercial", "BU", "BU-SAL"),
]


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    url = url or settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        settings.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return create_engine(url, future=True)


def synthetic_tables(regenerate: bool = False) -> dict[str, pd.DataFrame]:
    """Committed CSVs are the source of truth for the demo; regenerate=True rebuilds them from the generator."""
    from src.synthetic.generator import generate, write_csvs

    names = [t for t in schema.SYNTHETIC_TABLES]
    if regenerate or not all((settings.SYNTHETIC_DIR / f"{n}.csv").exists() for n in names):
        tables = generate()
        write_csvs(tables)
    return {n: pd.read_csv(settings.SYNTHETIC_DIR / f"{n}.csv") for n in names}


def public_tables() -> dict[str, pd.DataFrame]:
    from src.rag.corpus import load_chunks

    out: dict[str, pd.DataFrame] = {}
    if settings.HPE_SOURCES_CSV.exists():
        out["hpe_sources"] = pd.read_csv(settings.HPE_SOURCES_CSV)
    if settings.HPE_PRODUCTS_CSV.exists():
        out["hpe_products"] = pd.read_csv(settings.HPE_PRODUCTS_CSV)
    from src.public import hpe

    fin = hpe.financial_rows()
    if fin:
        out["hpe_financials"] = pd.DataFrame(fin)
    chunks = load_chunks()
    if chunks:
        out["documents"] = pd.DataFrame(chunks)
    return out


def build_database(url: str | None = None, regenerate: bool = False) -> Engine:
    from src.security.auth import hash_password

    engine = get_engine(url)
    schema.metadata.drop_all(engine)
    schema.metadata.create_all(engine)
    tables = {**synthetic_tables(regenerate), **public_tables()}
    with engine.begin() as conn:
        for name, df in tables.items():
            table = schema.metadata.tables[name]
            cols = [c.name for c in table.columns]
            df = df.copy()
            if "data_label" in cols:
                df["data_label"] = "SYNTHETIC"
            df = df[[c for c in cols if c in df.columns]]
            records = json.loads(df.to_json(orient="records"))  # NaN -> None, numpy -> python
            if records:
                conn.execute(insert(table), records)
        conn.execute(insert(schema.users), [
            {"user_id": u, "display_name": n, "role": r, "bu_id": bu, "password_hash": hash_password(settings.DEMO_PASSWORD)}
            for u, n, r, bu in DEMO_USERS])
    from src.db.views import materialise

    materialise(engine)
    return engine


def _has_rows(engine: Engine, table: str) -> bool:
    with engine.connect() as conn:
        try:
            return bool(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar())
        except Exception:
            return False


def ensure_base_database() -> Engine:
    """Base tables only (used by the analytics repository)."""
    engine = get_engine()
    return engine if _has_rows(engine, "ai_initiatives") else build_database()


def ensure_database() -> Engine:
    """Base tables plus the materialised semantic views."""
    engine = ensure_base_database()
    if not _has_rows(engine, "ai_initiative_metrics"):
        from src.db.views import materialise

        materialise(engine)
    return engine


def read_table(name: str, engine: Engine | None = None) -> pd.DataFrame:
    if name not in schema.metadata.tables:
        raise KeyError(f"unknown table {name}")
    engine = engine or ensure_base_database()
    with engine.connect() as conn:
        return pd.read_sql_table(name, conn)


if __name__ == "__main__":
    import sys

    eng = build_database(regenerate="--regenerate" in sys.argv)
    with eng.connect() as c:
        for t in schema.metadata.sorted_tables:
            print(f"{t.name:26s} {c.execute(text(f'SELECT COUNT(*) FROM {t.name}')).scalar():6d}")
