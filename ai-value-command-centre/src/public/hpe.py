"""PUBLIC HPE information: normalises the cited research pack in data/public into database tables.

* hpe_financials.json: values read from HPE's SEC filings (10-K FY2025, 10-Qs and 8-K earnings releases FY2026).
* hpe_ai_facts.json: AI-related facts with verbatim quotes, source URL and date.
* hpe_documents/*.md: single-source summaries used as the RAG corpus.

The product catalogue below maps the initiative categories to HPE portfolio names. Each description paraphrases a
cited public source only; no product capability is asserted without a source.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from src import settings
from src.rag.corpus import parse_document

TENK = "https://www.sec.gov/Archives/edgar/data/1645590/000164559025000130/hpe-20251031.htm"
PCAI_RELEASE = "https://nvidianews.nvidia.com/news/hpe-nvidia-ai-computing-generative-ai"

PRODUCTS = [
    # product_id, name, category, public description (paraphrase of the cited source), fact id / doc used
    ("HPE-PCAI", "HPE Private Cloud AI", "HPE Private Cloud AI",
     "Announced June 2024 as a key offering of 'NVIDIA AI Computing by HPE': a co-developed private cloud for AI combining "
     "NVIDIA AI computing, networking and software with HPE AI storage, compute and HPE GreenLake cloud; offered in four "
     "right-sized configurations.", "AI-19"),
    ("HPE-NVIDIA", "NVIDIA AI Computing by HPE", "AI ecosystem",
     "Portfolio of co-developed HPE and NVIDIA AI solutions with joint go-to-market, including system-integrator partners.", "AI-21"),
    ("HPE-GL", "HPE GreenLake cloud", "HPE GreenLake",
     "Described in HPE's FY2025 10-K as a centrepiece of HPE's strategy, offering a hybrid cloud experience with pay-per-use "
     "consumption; 52,000 customers in Q3 FY2026.", "AI-29"),
    ("HPE-OPSRAMP", "HPE OpsRamp", "HPE GreenLake",
     "IT operations management / observability software acquired in 2023 and integrated with HPE GreenLake; an OpsRamp AI "
     "copilot was announced as part of Private Cloud AI.", "AI-22"),
    ("HPE-PROLIANT", "HPE ProLiant servers", "AI Infrastructure",
     "Compute servers named in the Private Cloud AI infrastructure stack; server revenue sits in HPE's Cloud & AI segment "
     "from FY2026.", "AI-20"),
    ("HPE-CRAY", "HPE Cray supercomputing", "AI Infrastructure",
     "HPE Cray EX systems powered the three exascale systems on the November 2024 TOP500 list; the 10-K cites "
     "supercomputing and direct liquid cooling as AI differentiators.", "AI-35"),
    ("HPE-ALLETRA", "HPE Alletra Storage MP", "Storage",
     "HPE storage platform; over 7,400 Alletra MP arrays shipped by the end of FY2025, and the X10000 achieved NVIDIA-Certified "
     "Storage (foundation level) per NVIDIA in June 2026.", "AI-36"),
    ("HPE-ARUBA", "HPE Aruba Networking", "Networking",
     "HPE's networking portfolio, reported in the Networking segment (FY2025 revenue $6.85B).", "FIN"),
    ("HPE-JUNIPER", "HPE Juniper Networking (Mist AI)", "Networking",
     "Juniper Networks, acquired on 2 July 2025, doubling HPE's networking business; the DOJ settlement required limited "
     "access to Juniper's Mist AI technology.", "AI-31"),
    ("HPE-SERVICES", "HPE Services", "Services",
     "HPE Advisory and Professional Services offer consultative-led services and implementation; HPE Financial Services "
     "offers financing to help customers adopt technology including AI.", "AI-38"),
]


def _load(path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def financial_rows() -> list[dict]:
    raw = _load(settings.HPE_FINANCIALS_JSON)
    rows = []
    for key in ("annual", "annual_segments", "fy2026_quarterly", "fy2026_quarterly_segments"):
        for x in raw.get(key, []):
            rows.append({"metric": x["metric"], "segment": x.get("segment", "Total company"), "period": x["period"],
                         "value": x["value"], "unit": x.get("unit", "USD"), "source_id": source_id_for(x["url"]),
                         "note": f"{x.get('concept_or_label', '')} | {x.get('source_document', '')} | filed {x.get('filing_date', '')}"})
    return rows


def ai_facts() -> list[dict]:
    return _load(settings.HPE_AI_FACTS_JSON).get("facts", [])


_SOURCE_IDS: dict[str, str] = {}


def source_rows() -> list[dict]:
    """Every distinct public URL used anywhere (documents, facts, financials), with a stable id."""
    seen: dict[str, dict] = {}

    def add(url, title, date, stype, topic):
        url = url.strip()
        if url and url not in seen:
            seen[url] = {"title": title, "publisher": _publisher(url), "url": url, "date": str(date)[:10],
                         "source_type": stype, "topic": topic}

    for path in sorted(settings.HPE_DOCS_DIR.glob("*.md")):
        meta, _ = parse_document(path.read_text())
        if meta.get("url"):
            add(meta["url"], meta.get("title", path.stem), meta.get("date", ""), meta.get("source_type", ""), meta.get("topic", ""))
    for f in ai_facts():
        add(f["url"], f["source_title"], f["date"], f["source_type"], f["topic"])
    raw = _load(settings.HPE_FINANCIALS_JSON)
    for key in ("annual", "annual_segments", "fy2026_quarterly", "fy2026_quarterly_segments"):
        for x in raw.get(key, []):
            add(x["url"], x.get("source_document", "SEC filing"), x.get("filing_date", ""), "SEC filing", "financials")
    rows = []
    for i, (url, r) in enumerate(sorted(seen.items(), key=lambda kv: (kv[1]["date"], kv[0])), start=1):
        sid = f"SRC-{i:02d}"
        _SOURCE_IDS[url] = sid
        rows.append({"source_id": sid, **r})
    return rows


def source_id_for(url: str) -> str | None:
    if not _SOURCE_IDS:
        source_rows()
    return _SOURCE_IDS.get(url.strip())


def product_rows() -> list[dict]:
    facts = {f["id"]: f for f in ai_facts()}
    out = []
    for pid, name, cat, desc, ref in PRODUCTS:
        url = facts[ref]["url"] if ref in facts else TENK
        out.append({"product_id": pid, "name": name, "category": cat, "public_description": desc, "source_id": source_id_for(url)})
    return out


def _publisher(url: str) -> str:
    host = re.sub(r"^https?://", "", url).split("/")[0]
    return {"www.sec.gov": "U.S. SEC (EDGAR)", "investors.hpe.com": "HPE Investor Relations", "nvidianews.nvidia.com": "NVIDIA Newsroom",
            "blogs.nvidia.com": "NVIDIA Blog", "developer.hpe.com": "HPE Developer", "www.top500.org": "TOP500",
            "data.sec.gov": "U.S. SEC (XBRL API)"}.get(host, host)


def write_reference_csvs() -> None:
    pd.DataFrame(source_rows()).to_csv(settings.HPE_SOURCES_CSV, index=False)
    pd.DataFrame(product_rows()).to_csv(settings.HPE_PRODUCTS_CSV, index=False)


def headline() -> dict:
    """A compact public HPE fact sheet for the UI (all values from filings / company disclosures)."""
    fin = pd.DataFrame(financial_rows())
    if fin.empty:
        return {}

    def v(metric, period, segment="Total company"):
        x = fin[(fin.metric == metric) & (fin.period == period) & (fin.segment == segment)]
        return (float(x.value.iloc[0]), x.source_id.iloc[0]) if len(x) else (None, None)

    out = {"annual": {}, "segments_fy2025": {}, "q3_fy2026": {}, "segments_q3_fy2026": {}}
    for m in ("total_net_revenue", "gross_profit", "earnings_from_operations", "net_earnings_attributable_to_HPE",
              "research_and_development", "net_cash_from_operating_activities", "free_cash_flow_non_GAAP"):
        out["annual"][m] = {p: v(m, p)[0] for p in ("FY2023", "FY2024", "FY2025")}
    for seg in sorted(set(fin[(fin.period == "FY2025") & (fin.segment != "Total company")].segment)):
        out["segments_fy2025"][seg] = {"revenue": v("segment_net_revenue", "FY2025", seg)[0],
                                       "operating_profit": v("segment_earnings_from_operations", "FY2025", seg)[0]}
    for m in ("total_net_revenue", "gross_profit", "earnings_from_operations"):
        out["q3_fy2026"][m] = v(m, "Q3 FY2026")[0]
    for seg in sorted(set(fin[(fin.period == "Q3 FY2026") & (fin.segment != "Total company")].segment)):
        out["segments_q3_fy2026"][seg] = {"revenue": v("segment_net_revenue", "Q3 FY2026", seg)[0],
                                          "operating_profit": v("segment_earnings_from_operations", "Q3 FY2026", seg)[0]}
    out["ai_facts"] = [{k: f[k] for k in ("id", "topic", "claim", "quote", "source_title", "url", "date")} for f in ai_facts()]
    out["label"] = settings.PUBLIC_LABEL
    return out


if __name__ == "__main__":
    write_reference_csvs()
    print(len(source_rows()), "sources;", len(product_rows()), "products;", len(financial_rows()), "financial values")
