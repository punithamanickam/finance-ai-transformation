"""Source registry: the list of public documents the system is allowed to use."""
from __future__ import annotations

import json

import pandas as pd

from src import settings

SHORT_NAMES = {
    "MSFT-10K-FY2026": "Microsoft FY2026 Form 10-K",
    "MSFT-10K-FY2025": "Microsoft FY2025 Form 10-K",
    "MSFT-8K-FY26Q4-EX99": "Microsoft Q4 FY2026 earnings release (Form 8-K Ex. 99.1)",
    "MSFT-XBRL-COMPANYFACTS": "SEC XBRL Company Facts (Microsoft)",
    "MSFT-IR": "Microsoft Investor Relations",
}


def load_registry() -> pd.DataFrame:
    df = pd.read_csv(settings.SOURCE_REGISTRY, dtype=str).fillna("")
    df["short_name"] = df["source_id"].map(SHORT_NAMES).fillna(df["document_name"])
    return df


def write_source_cards() -> None:
    """One JSON card per source in data/sources/ (URL, document, period, retrieval date, type)."""
    settings.SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    for _, r in load_registry().iterrows():
        card = {k: r[k] for k in ["source_id", "document_name", "source_type", "reporting_period", "filing_date",
                                  "retrieval_date", "source_url", "accession_number", "role", "notes"]}
        (settings.SOURCES_DIR / f"{r['source_id']}.json").write_text(json.dumps(card, indent=2) + "\n")
