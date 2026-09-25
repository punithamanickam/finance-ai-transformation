"""Research / RAG Agent: answers questions about HPE's public AI portfolio and financials, always with citations.

Order of evidence: (1) figures read from HPE's SEC filings (structured table), (2) curated AI facts with verbatim
quotes, (3) retrieved passages from the public document corpus. If nothing relevant is retrieved, the agent says
so instead of answering from model memory.
"""
from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src import settings
from src.agents.base import Agent, Number
from src.copilot.response import EvidenceRef, money
from src.public import hpe
from src.rag.retriever import get_retriever

METRICS = [
    (r"gross (profit|margin)", "gross_profit", "Gross profit"),
    (r"operating (profit|income|earnings)|earnings from operations", "earnings_from_operations", "Earnings from operations"),
    (r"net (earnings|income|profit)", "net_earnings_attributable_to_HPE", "Net earnings"),
    (r"free cash flow|\bfcf\b", "free_cash_flow_non_GAAP", "Free cash flow (non-GAAP)"),
    (r"operating cash|cash from operations", "net_cash_from_operating_activities", "Operating cash flow"),
    (r"r&d|research and development", "research_and_development", "R&D expense"),
    (r"\beps\b|earnings per share", "diluted_EPS", "Diluted EPS"),
    (r"revenue|sales", "total_net_revenue", "Total net revenue"),
]
SEGMENTS = ["Cloud & AI", "Networking", "Server", "Hybrid Cloud", "Financial Services", "Corporate Investments and Other"]


@lru_cache(maxsize=1)
def _facts_index():
    facts = hpe.ai_facts()
    vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
    mat = vec.fit_transform([f"{f['topic']} {f['claim']} {f['quote']}" for f in facts]) if facts else None
    return facts, vec, mat


def search_facts(query: str, k: int = 3, min_score: float = 0.08) -> list[dict]:
    facts, vec, mat = _facts_index()
    if mat is None:
        return []
    s = cosine_similarity(vec.transform([query]), mat).ravel()
    order = s.argsort()[::-1][:k]
    return [{**facts[i], "score": float(s[i])} for i in order if s[i] >= min_score]


def lookup_financial(question: str) -> dict | None:
    ql = question.lower()
    metric = next(((m, label) for pat, m, label in METRICS if re.search(pat, ql)), None)
    if not metric:
        return None
    fin = pd.DataFrame(hpe.financial_rows())
    seg = next((s for s in SEGMENTS if s.lower() in ql or (s == "Cloud & AI" and "cloud and ai" in ql)), None)
    m = re.search(r"q([1-4])\s*(?:fy)?\s*(20\d\d|\d\d)", ql) or re.search(r"(?:fy)?\s*(20\d\d)\s*q([1-4])", ql)
    period = None
    if m and ql[m.start()] == "q":
        yr = m.group(2) if len(m.group(2)) == 4 else "20" + m.group(2)
        period = f"Q{m.group(1)} FY{yr}"
    elif m:
        period = f"Q{m.group(2)} FY{m.group(1)}"
    else:
        y = re.search(r"(?:fy|fiscal(?: year)?)\s*(20\d\d|\d\d)\b|\b(20\d\d)\b", ql)
        if y:
            yr = y.group(1) or y.group(2)
            period = f"FY{yr if len(yr) == 4 else '20' + yr}"
    rows = fin[(fin.metric == ("segment_net_revenue" if seg and metric[0] == "total_net_revenue" else
                               "segment_earnings_from_operations" if seg and metric[0] == "earnings_from_operations" else metric[0]))]
    rows = rows[rows.segment == seg] if seg else rows[rows.segment == "Total company"]
    if rows.empty:
        return None
    if period is None or period not in set(rows.period):
        period = "Q3 FY2026" if "latest" in ql or "quarter" in ql and "Q3 FY2026" in set(rows.period) else (
            "FY2025" if "FY2025" in set(rows.period) else rows.period.iloc[-1])
    r = rows[rows.period == period]
    if r.empty:
        return None
    r = r.iloc[0]
    src = pd.DataFrame(hpe.source_rows()).set_index("source_id")
    s = src.loc[r.source_id] if r.source_id in src.index else None
    series = rows[rows.period.str.startswith("FY") == period.startswith("FY")][["period", "value"]].to_dict("records")
    return {"metric": metric[1], "segment": seg, "period": period, "value": float(r.value), "unit": r.unit,
            "source_id": r.source_id, "source_title": s.title if s is not None else "", "url": s.url if s is not None else "",
            "date": s.date if s is not None else "", "note": r.note, "series": series}


class ResearchAgent(Agent):
    name = "Research / RAG Agent"

    def answer(self, q: str):
        fin = lookup_financial(q)
        facts = search_facts(q, min_score=0.25 if fin else 0.08)
        passages = get_retriever().search(q, k=3)
        if not (fin or facts or passages):
            return self.respond(q, "hpe_research", "The public HPE corpus does not contain information that answers this question, so no answer is given.",
                                confidence={"level": "Low", "basis": "No relevant passage retrieved; the agent does not answer from model memory."},
                                data_label=settings.PUBLIC_LABEL)
        parts, numbers, evidence = [], [], []
        if fin:
            unit = "USD" if fin["unit"] == "USD" else "count"
            label = (f"{fin['segment']} segment {fin['metric'].lower().replace('total net ', '').replace('earnings from operations', 'operating profit')}"
                     if fin["segment"] else fin["metric"].lower())
            val = money(fin["value"]) if unit == "USD" else f"{fin['value']:.2f}"
            parts.append(f"HPE reported {label} of {val} for {fin['period']} [{fin['source_id']}].")
            if len(fin["series"]) > 1 and fin["period"].startswith("FY"):
                parts.append("Trend: " + ", ".join(f"{x['period']} {money(x['value']) if unit == 'USD' else x['value']}" for x in fin["series"]) + ".")
            numbers.append(Number(f"HPE {label} ({fin['period']})", fin["value"], unit, basis="public", display=val))
            evidence.append(EvidenceRef("public_financials", fin["source_title"], fin["source_id"], fin["note"], fin["url"], fin["date"]))
        for f in facts[: (2 if fin else 3)]:
            parts.append(f"{f['claim']} [{f['id']}]")
            evidence.append(EvidenceRef("document", f["source_title"], f["id"], f.get("note", ""), f["url"], f["date"], f["quote"]))
        for p in passages:
            evidence.append(EvidenceRef("document", p["title"], p["chunk_id"], f"{p['source_type']}; retrieval score {p['score']}", p["url"], p["date"],
                                        " ".join(get_retriever().best_sentences(p["text"], q, 2))))
        if not fin and not facts and passages:
            parts.append(" ".join(get_retriever().best_sentences(passages[0]["text"], q, 2)) + f" [{passages[0]['chunk_id']}]")
        filing = fin is not None or any("10-" in str(f.get("source_type", "")) for f in facts)
        return self.respond(
            q, "hpe_research", " ".join(parts),
            key_drivers=[f"{e.label} ({e.date})" for e in evidence[:4]],
            numbers=numbers, evidence=evidence,
            confidence={"level": "High" if filing else "Medium",
                        "basis": ("Figures read from HPE SEC filings." if fin else "")
                        + (" AI order, backlog and customer metrics are company-reported KPIs (unaudited)." if facts else "")
                        + " Every statement is cited; nothing is answered from model memory."},
            data_label=settings.PUBLIC_LABEL,
            follow_ups=["How is our portfolio mapped to HPE technology categories?"])

    def portfolio_mapping(self, q: str):
        t = self.ctx.table
        prods = self.ctx.repo["hpe_products"].set_index("product_id")
        srcs = self.ctx.repo["hpe_sources"].set_index("source_id")
        by = t.groupby("hpe_category").agg(n=("initiative_id", "count"), investment=("investment", "sum"), realised=("realised_value", "sum"))
        ev = []
        for pid, p in prods.iterrows():
            s = srcs.loc[p.source_id] if p.source_id in srcs.index else None
            ev.append(EvidenceRef("document", f"{p['name']}: {p.public_description}", p.source_id, p.category,
                                  s.url if s is not None else None, s.date if s is not None else None))
        return self.respond(
            q, "hpe_mapping",
            "Initiatives are mapped to HPE portfolio categories: " + "; ".join(f"{c}: {int(r.n)} initiative(s), {money(r.investment)} invested, {money(r.realised)} realised"
                                                                              for c, r in by.sort_values("investment", ascending=False).iterrows()) + ".",
            key_drivers=[f"{r['name']} -> {r.hpe_category} ({r.hpe_product_ids.replace(',', ', ')})" for _, r in t.iterrows()],
            evidence=ev,
            confidence={"level": "High", "basis": "Mapping is a synthetic design choice; each HPE product description paraphrases a cited public source."},
            data_label=settings.SYNTHETIC_LABEL + " | " + settings.PUBLIC_LABEL)
