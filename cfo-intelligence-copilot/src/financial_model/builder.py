"""Build the normalised financial model from extracted XBRL facts + deterministic text patterns.

Rules
-----
* Only 12-month fiscal-year durations (and fiscal-year-end instants) enter the annual model.
* A fact repeated inside one filing (statement, MD&A table, note) must agree everywhere; otherwise it is
  marked ``consistency = conflict`` and the copilot refuses to use it without manual review.
* When two filings report the same period (e.g. FY2025 in both the FY2025 and FY2026 10-K), the most recent
  filing is authoritative (comparatives may be recast). Differences are logged to ``source_conflicts.csv``
  and the fact carries ``restated_vs_prior_filing = True``.
"""
from __future__ import annotations

import json
import re
from datetime import date

import pandas as pd

from src import settings
from src.ingestion.document_parser import Page
from src.ingestion.source_registry import load_registry

TOLERANCE = 0.5  # USD millions - rounding tolerance for "same value"


def load_metric_map() -> dict:
    return json.loads(settings.METRIC_MAP.read_text())


def _is_annual(row) -> bool:
    if row["period_type"] == "instant":
        return int(row["period_end"][5:7]) == 6
    d0 = date.fromisoformat(row["period_start"])
    d1 = date.fromisoformat(row["period_end"])
    return 355 <= (d1 - d0).days <= 372


def _base_record(metric: dict, occ: pd.DataFrame, src: dict, company: str) -> dict:
    pref = metric.get("prefer_table", "")
    occ = occ.copy()
    occ["_pref"] = occ["table_title"].str.upper().str.replace(" ", "").str.contains(pref.upper().replace(" ", ""), regex=False) if pref else False
    primary = occ.sort_values(["_pref", "page"], ascending=[False, True]).iloc[0]
    distinct = occ["value"].round(3).unique()
    consistent = (occ["value"].max() - occ["value"].min()) <= TOLERANCE
    fy = int(primary["fiscal_year"])
    return {
        "company": company,
        "reporting_period": f"FY{fy}",
        "fiscal_year": fy,
        "period_end": primary["period_end"],
        "period_type": primary["period_type"],
        "statement": metric["statement"],
        "section": metric["section"],
        "metric_id": metric["metric_id"],
        "metric_label": metric["label"],
        "value": float(primary["value"]),
        "currency": primary["currency"],
        "unit": primary["unit"],
        "source_id": src["source_id"],
        "source_document": src["short_name"],
        "source_page": int(primary["page"]),
        "source_section": primary["section"],
        "source_table": (primary["table_title"] or primary["heading"] or "")[:160],
        "table_index": None if pd.isna(primary["table_index"]) else int(primary["table_index"]),
        "row_label": primary["row_label"],
        "column_label": primary["column_label"],
        "source_url": src["source_url"],
        "xbrl_concept": primary["concept"],
        "xbrl_fact_id": primary["fact_id"],
        "extraction_method": "ixbrl",
        "occurrences": int(len(occ)),
        "consistency": "consistent" if consistent else "conflict",
        "_distinct_values": ";".join(str(v) for v in distinct),
    }


def build_from_filing(facts: pd.DataFrame, source_id: str, pages: list[Page] | None = None) -> pd.DataFrame:
    mm = load_metric_map()
    reg = load_registry().set_index("source_id")
    src = reg.loc[source_id].to_dict()
    src["source_id"] = source_id
    company = mm["company"]["name"]
    facts = facts[facts.apply(_is_annual, axis=1)].copy()
    facts["dimensions"] = facts["dimensions"].fillna("")
    records: list[dict] = []

    def add(metric: dict, occ: pd.DataFrame, dim_type="", member="", dim_label=""):
        for fy, grp in occ.groupby("fiscal_year"):
            r = _base_record(metric, grp, src, company)
            r.update(dimension_type=dim_type, dimension_member=member, dimension_label=dim_label)
            records.append(r)

    # 1. canonical statement metrics
    for m in mm["metrics"]:
        ptype = m.get("period_type", "duration")
        occ = facts[(facts.concept == m["concept"]) & (facts.dimensions == m.get("dimensions", "")) & (facts.period_type == ptype)]
        if not occ.empty:
            add(m, occ)

    # 2. segment P&L
    seg_axis = mm["segment_axis"]
    for seg in mm["segments"]:
        dim = f"{seg_axis}={seg['member']}"
        for sm in mm["segment_metrics"]:
            occ = facts[(facts.concept == sm["concept"]) & (facts.dimensions == dim)]
            if not occ.empty:
                metric = {**sm, "statement": "Segment", "section": "Note - Segment Information and Geographic Data", "prefer_table": ""}
                add(metric, occ, "segment", seg["segment_id"], seg["name"])

    # 3. revenue by product / service offering (discovered from the filing, not hard-coded)
    prod_axis = mm["product_axis"]
    rev = facts[(facts.concept == mm["revenue_concept"]) & facts.dimensions.str.startswith(prod_axis + "=")]
    rev = rev[~rev.dimensions.str.contains("ProductMember$|ServiceOtherMember$", regex=True)]
    rev = rev[~rev.dimensions.str.contains(";")]
    for dim, occ in rev.groupby("dimensions"):
        member = dim.split("=")[1]
        label = occ.sort_values("page").iloc[0]["row_label"] or member.split(":")[-1]
        metric = {"metric_id": "revenue_by_offering", "label": "Revenue by product/service offering", "statement": "Notes",
                  "section": "Note - Segment Information and Geographic Data", "prefer_table": ""}
        add(metric, occ, "product_offering", member.split(":")[-1], re.sub(r"\s*\(.*?\)$", "", label))

    # 4. deterministic text-pattern metrics (e.g. headcount)
    if pages:
        for tm in mm.get("text_metrics", []):
            pat = re.compile(tm["pattern"])
            for pg in pages:
                for b in pg.blocks:
                    for mt in pat.finditer(b.text):
                        fy = int(mt.group("year"))
                        records.append({
                            "company": company, "reporting_period": f"FY{fy}", "fiscal_year": fy,
                            "period_end": f"{fy}-06-30", "period_type": "instant", "statement": tm["statement"],
                            "section": tm["section"], "metric_id": tm["metric_id"], "metric_label": tm["label"],
                            "value": float(mt.group("value").replace(",", "")), "currency": tm["currency"], "unit": tm["unit"],
                            "source_id": source_id, "source_document": src["short_name"], "source_page": pg.page_number,
                            "source_section": pg.section, "source_table": b.heading or tm["section"], "table_index": None,
                            "row_label": "", "column_label": "", "source_url": src["source_url"], "xbrl_concept": "",
                            "xbrl_fact_id": "", "extraction_method": "text-pattern", "occurrences": 1,
                            "consistency": "consistent", "dimension_type": "", "dimension_member": "",
                            "dimension_label": "", "_distinct_values": mt.group("value"),
                        })
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["metric_id", "fiscal_year", "dimension_member"], keep="first")
    df["fact_key"] = df["metric_id"] + "|FY" + df["fiscal_year"].astype(str) + "|" + df["dimension_member"]
    return df


def merge_filings(frames: list[pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """frames ordered from most recent (authoritative) to oldest."""
    conflicts = []
    merged = frames[0].copy()
    merged["restated_vs_prior_filing"] = False
    for older in frames[1:]:
        o = older.set_index("fact_key")
        for i, row in merged.iterrows():
            if row["fact_key"] in o.index:
                ov = float(o.loc[row["fact_key"], "value"])
                if abs(ov - row["value"]) > TOLERANCE:
                    merged.at[i, "restated_vs_prior_filing"] = True
                    conflicts.append({
                        "conflict_type": "cross_filing_difference",
                        "fact_key": row["fact_key"], "metric_label": row["metric_label"], "dimension_label": row["dimension_label"],
                        "value_used": row["value"], "value_used_source": row["source_id"], "value_used_page": row["source_page"],
                        "other_value": ov, "other_source": o.loc[row["fact_key"], "source_id"],
                        "other_page": int(o.loc[row["fact_key"], "source_page"]),
                        "resolution": "Most recent filing is authoritative (comparative restated / recast). Flagged for review.",
                    })
        new = older[~older["fact_key"].isin(merged["fact_key"])].copy()
        # For a (metric, year) the newer filing already reports, older-filing dimension members that no longer exist
        # (e.g. renamed product lines) are superseded - adding them would double count.
        covered = set(zip(merged["metric_id"], merged["fiscal_year"]))
        superseded = new[[(m, y) in covered for m, y in zip(new["metric_id"], new["fiscal_year"])]]
        for _, r in superseded.iterrows():
            conflicts.append({
                "conflict_type": "superseded_member", "fact_key": r["fact_key"], "metric_label": r["metric_label"],
                "dimension_label": r["dimension_label"], "value_used": float("nan"), "value_used_source": frames[0]["source_id"].iloc[0],
                "value_used_page": "", "other_value": r["value"], "other_source": r["source_id"], "other_page": r["source_page"],
                "resolution": "Category renamed/recast in the most recent filing; older member excluded for this period.",
            })
        new = new.drop(superseded.index)
        new["restated_vs_prior_filing"] = False
        merged = pd.concat([merged, new], ignore_index=True)
    for _, row in merged[merged["consistency"] == "conflict"].iterrows():
        conflicts.append({
            "conflict_type": "intra_filing_conflict", "fact_key": row["fact_key"], "metric_label": row["metric_label"],
            "dimension_label": row["dimension_label"], "value_used": row["value"], "value_used_source": row["source_id"],
            "value_used_page": row["source_page"], "other_value": row["_distinct_values"], "other_source": row["source_id"],
            "other_page": "", "resolution": "BLOCKED - manual review required before use.",
        })
    merged = merged.drop(columns=["_distinct_values"])
    merged = merged.sort_values(["statement", "metric_id", "dimension_member", "fiscal_year"]).reset_index(drop=True)
    cols = ["fact_key"] + [c for c in merged.columns if c != "fact_key"]
    return merged[cols], pd.DataFrame(conflicts)
