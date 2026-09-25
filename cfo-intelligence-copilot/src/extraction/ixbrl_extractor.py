"""Financial data extraction from Inline XBRL.

Every numeric fact tagged in the filing is extracted together with full positional provenance:
document, page, 10-K section, table title, table index, row label, column label, XBRL concept,
reporting period, dimensions (e.g. segment member), unit and scale. Values are never typed in by hand.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

from src.ingestion.document_parser import ITEM_NAMES, _running_header, clean_text, split_pages

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


@dataclass
class XbrlFact:
    fact_id: str
    source_id: str
    concept: str
    value: float  # normalised: USD millions for monetary, USD for per-share, millions for shares, raw otherwise
    unit: str  # "USD millions" | "USD per share" | "shares millions" | "percent" | "pure" | ...
    currency: str
    raw_text: str
    scale: int
    decimals: str
    period_type: str  # "duration" | "instant"
    period_start: str
    period_end: str
    fiscal_year: int
    dimensions: str  # "axis=member;axis=member" or ""
    page: int
    section: str
    heading: str
    table_title: str
    table_index: int | None
    row_index: int | None
    row_label: str
    column_label: str


def _parse_contexts(soup: BeautifulSoup) -> dict[str, dict]:
    ctx = {}
    for c in soup.find_all("xbrli:context"):
        cid = c.get("id")
        dims = []
        for m in c.find_all("xbrldi:explicitmember"):
            dims.append(f"{m.get('dimension')}={clean_text(m.get_text())}")
        for m in c.find_all("xbrldi:typedmember"):
            dims.append(f"{m.get('dimension')}={clean_text(m.get_text())}")
        inst = c.find("xbrli:instant")
        if inst:
            ctx[cid] = {"type": "instant", "start": "", "end": clean_text(inst.get_text()), "dims": ";".join(sorted(dims))}
        else:
            s, e = c.find("xbrli:startdate"), c.find("xbrli:enddate")
            ctx[cid] = {
                "type": "duration",
                "start": clean_text(s.get_text()) if s else "",
                "end": clean_text(e.get_text()) if e else "",
                "dims": ";".join(sorted(dims)),
            }
    return ctx


def _parse_units(soup: BeautifulSoup) -> dict[str, str]:
    units = {}
    for u in soup.find_all("xbrli:unit"):
        uid = u.get("id")
        num = u.find("xbrli:unitnumerator")
        if num:
            n = clean_text(num.get_text())
            d = clean_text(u.find("xbrli:unitdenominator").get_text())
            units[uid] = f"{n.split(':')[-1]}/{d.split(':')[-1]}"
        else:
            m = u.find("xbrli:measure")
            units[uid] = clean_text(m.get_text()).split(":")[-1] if m else uid
    return units


def fiscal_year_from_end(end: str, fy_end_month: int = 6) -> int:
    y, m = int(end[:4]), int(end[5:7])
    return y if m <= fy_end_month else y + 1


def _num(text: str, fmt: str) -> float | None:
    if "zero" in (fmt or "") or text.strip() in {"—", "-", "–"}:
        return 0.0
    t = text.replace(",", "").replace("$", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def _txt(el: Tag) -> str:
    return clean_text(el.get_text(""))


def _grid_col(td: Tag) -> int:
    col = 0
    for sib in td.find_previous_siblings(["td", "th"]):
        col += int(sib.get("colspan", 1))
    return col


def _header_label(table: Tag, col: int, row_tr: Tag) -> str:
    labels = []
    for tr in table.find_all("tr"):
        if tr is row_tr or tr.find("ix:nonfraction") is not None:
            break  # header rows are the rows above the first data row
        if "visibility:collapse" in (tr.get("style") or ""):
            continue
        pos = 0
        for td in tr.find_all(["td", "th"]):
            span = int(td.get("colspan", 1))
            if pos <= col < pos + span + 1:
                t = _txt(td)
                if t and t not in {"$", "%"}:
                    labels.append(t)
                    break
            pos += span
    return " / ".join(labels[-2:])


def _row_label(tr: Tag) -> str:
    for td in tr.find_all(["td", "th"]):
        t = _txt(td)
        if t and not re.fullmatch(r"[\$\d,.()%\s—–-]+", t):
            return t
    return ""


def _table_title(table: Tag) -> str:
    for prev in table.find_all_previous(["p", "table"], limit=12):
        if prev.name == "table":
            break
        t = _txt(prev)
        if t and len(t) < 160:
            return t
    return ""


def extract_facts(path: str | Path, source_id: str) -> list[XbrlFact]:
    html = Path(path).read_text(encoding="utf-8", errors="ignore")
    head = BeautifulSoup(html[: html.find("</ix:header>") + 20] if "</ix:header>" in html else html, "lxml")
    contexts = _parse_contexts(head)
    units = _parse_units(head)
    facts: list[XbrlFact] = []
    last_item = ""
    for idx, raw in enumerate(split_pages(html)):
        if "nonfraction" not in raw.lower():
            # still track running header for section continuity
            last_item = _running_header(BeautifulSoup(raw[:4000], "lxml"))[1] or last_item
            continue
        soup = BeautifulSoup(raw, "lxml")
        header = soup.find("ix:header")
        if header:
            header.decompose()
        _, item = _running_header(soup)
        item = item or last_item
        last_item = item
        page_text_tail = clean_text(soup.get_text(" "))[-6:]
        m = re.search(r"(\d{1,3})$", page_text_tail)
        page_no = int(m.group(1)) if m and abs(int(m.group(1)) - (idx + 1)) <= 2 else idx + 1
        tables = soup.find_all("table")
        for el in soup.find_all("ix:nonfraction"):
            if el.get("xsi:nil") == "true":
                continue
            cref = el.get("contextref")
            c = contexts.get(cref)
            if not c or not c["end"]:
                continue
            fmt = el.get("format", "")
            val = _num(el.get_text(), fmt)
            if val is None:
                continue
            scale = int(el.get("scale", "0") or 0)
            if el.get("sign") == "-":
                val = -val
            unit_raw = units.get(el.get("unitref", ""), el.get("unitref", ""))
            absolute = val * (10**scale)
            if unit_raw == "USD":
                value, unit, cur = absolute / 1e6, "USD millions", "USD"
            elif unit_raw == "USD/shares":
                value, unit, cur = absolute, "USD per share", "USD"
            elif unit_raw == "shares":
                value, unit, cur = absolute / 1e6, "shares millions", ""
            elif unit_raw == "pure":
                value, unit, cur = absolute, "ratio", ""
            else:
                value, unit, cur = absolute, unit_raw, ""
            td = el.find_parent("td")
            tr = el.find_parent("tr")
            table = el.find_parent("table")
            heading_el = None
            for prev in el.find_all_previous("p", limit=400):
                sp = prev.find("span")
                if sp is not None and "underline" in (sp.get("style") or ""):
                    txt = _txt(prev)
                    if txt and not re.match(r"^PAR\s*T", txt):
                        heading_el = prev
                        break
            facts.append(
                XbrlFact(
                    fact_id=el.get("id", ""),
                    source_id=source_id,
                    concept=el.get("name", ""),
                    value=round(value, 6),
                    unit=unit,
                    currency=cur,
                    raw_text=clean_text(el.get_text()),
                    scale=scale,
                    decimals=el.get("decimals", ""),
                    period_type=c["type"],
                    period_start=c["start"],
                    period_end=c["end"],
                    fiscal_year=fiscal_year_from_end(c["end"]),
                    dimensions=c["dims"],
                    page=page_no,
                    section=ITEM_NAMES.get(item, f"Item {item}"),
                    heading=_txt(heading_el)[:160] if heading_el else "",
                    table_title=_table_title(table) if table else "",
                    table_index=tables.index(table) if table in tables else None,
                    row_index=(table.find_all("tr").index(tr) if (table and tr) else None),
                    row_label=_row_label(tr) if tr else "",
                    column_label=_header_label(table, _grid_col(td), tr) if (table and td and tr) else "",
                )
            )
    return facts


def extract_to_frame(path: str | Path, source_id: str) -> pd.DataFrame:
    return pd.DataFrame([asdict(f) for f in extract_facts(path, source_id)])
