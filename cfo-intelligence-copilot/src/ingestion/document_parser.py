"""Document intelligence: split an SEC HTML/iXBRL filing into pages, sections, headings, paragraphs and tables.

The parser preserves the provenance required downstream: document, page, section (10-K Item), sub-heading,
table index and row. It is deliberately format-aware rather than a generic "PDF to text" step.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

PAGE_BREAK = re.compile(r"<hr[^>]*>", re.IGNORECASE)

ITEM_NAMES = {
    "1": "Item 1. Business",
    "1A": "Item 1A. Risk Factors",
    "1B": "Item 1B. Unresolved Staff Comments",
    "1C": "Item 1C. Cybersecurity",
    "2": "Item 2. Properties",
    "3": "Item 3. Legal Proceedings",
    "4": "Item 4. Mine Safety Disclosures",
    "5": "Item 5. Market for Registrant's Common Equity",
    "6": "Item 6. [Reserved]",
    "7": "Item 7. Management's Discussion and Analysis (MD&A)",
    "7A": "Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Item 8. Financial Statements and Supplementary Data",
    "9": "Item 9. Changes in and Disagreements with Accountants",
    "9A": "Item 9A. Controls and Procedures",
    "9B": "Item 9B. Other Information",
    "10": "Item 10. Directors, Executive Officers and Corporate Governance",
    "12": "Item 12. Security Ownership",
    "15": "Item 15. Exhibits and Financial Statement Schedules",
    "16": "Item 16. Form 10-K Summary",
}


def clean_text(s: str) -> str:
    s = s.replace("\xa0", " ").replace("​", "")
    s = re.sub(r"\s+", " ", s)
    # iXBRL splits negative numbers as "( 4,901 )"
    s = re.sub(r"\(\s+([\d.,]+)\s+\)", r"(\1)", s)
    return s.strip()


@dataclass
class Block:
    kind: str  # "heading" | "paragraph" | "table"
    text: str
    heading: str = ""  # nearest preceding heading on the page
    table_index: int | None = None
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class Page:
    page_number: int
    part: str
    item_code: str
    section: str
    blocks: list[Block]
    html: str = ""  # raw page html (used by the XBRL extractor for positional provenance)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks)


def _is_minor_heading(text: str) -> bool:
    """Short title-like line (e.g. a segment name in MD&A): no sentence punctuation, no numbers."""
    words = text.split()
    return (0 < len(words) <= 8 and not text.endswith((".", ":", ";", ",")) and not any(c.isdigit() for c in text)
            and text[0].isupper() and "|" not in text)


def _is_heading(p: Tag, text: str) -> bool:
    if not text or len(text) > 140 or text.endswith("."):
        return False
    spans = [s for s in p.find_all("span") if clean_text(s.get_text())]
    if not spans:
        return False
    styled = all(
        ("underline" in (s.get("style") or "")) or ("font-weight:bold" in (s.get("style") or "")) for s in spans
    )
    upper = text.upper() == text and any(c.isalpha() for c in text) and len(text) > 3
    return styled or upper


def _table_rows(table: Tag) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        if "visibility:collapse" in (tr.get("style") or ""):
            continue
        cells = [clean_text(td.get_text("")) for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c and c not in {"$", "%", ")"}]
        if cells:
            rows.append(cells)
    return rows


def _running_header(soup: BeautifulSoup) -> tuple[str, str]:
    first = soup.find("div")
    txt = clean_text(first.get_text(" ")) if first else ""
    part_m = re.search(r"PART\s*([IV]+)", txt.replace(" ", "")) or re.search(r"PAR\s*T\s*([IV]+)", txt)
    item_m = re.search(r"Item\s+([0-9]{1,2}[A-C]?)", txt)
    return (f"Part {part_m.group(1)}" if part_m else "", item_m.group(1) if item_m else "")


def split_pages(html: str) -> list[str]:
    return PAGE_BREAK.split(html)


def parse_filing(path: str | Path, keep_html: bool = False) -> list[Page]:
    html = Path(path).read_text(encoding="utf-8", errors="ignore")
    raw_pages = split_pages(html)
    pages: list[Page] = []
    last_item = ""
    major = minor = ""  # heading context carries across page breaks
    for idx, raw in enumerate(raw_pages):
        soup = BeautifulSoup(raw, "lxml")
        for hidden in soup.find_all(["ix:header"]):
            hidden.decompose()
        part, item = _running_header(soup)
        item = item or last_item
        last_item = item
        body = soup.find("div", class_="main-content-container") or soup.body or soup
        blocks: list[Block] = []
        if item != (pages[-1].item_code if pages else None):
            major = minor = ""
        t_index = 0
        for el in body.find_all(["p", "table"], recursive=True):
            if el.find_parent("table") is not None:
                continue  # table content is captured with the table
            heading = " › ".join(h for h in (major, minor) if h)
            if el.name == "table":
                rows = _table_rows(el)
                if rows:
                    blocks.append(
                        Block("table", "\n".join(" | ".join(r) for r in rows), heading, t_index, rows)
                    )
                    t_index += 1
                continue
            text = clean_text(el.get_text(""))
            if not text:
                continue
            if _is_heading(el, text):
                if text.startswith("Fiscal Year") and minor:
                    minor = minor.split(" › ")[0] + " › " + text  # period marker keeps the topic heading
                elif text.upper() == text or "underline" in str(el):
                    major, minor = text, ""
                else:
                    minor = text
                blocks.append(Block("heading", text, " › ".join(h for h in (major, minor) if h)))
            elif _is_minor_heading(text) and item in {"7", "7A", "8"}:
                minor = text
                blocks.append(Block("heading", text, " › ".join(h for h in (major, minor) if h)))
            else:
                blocks.append(Block("paragraph", text, heading))
        # page number: trailing integer footer, else sequential
        page_no = idx + 1
        if blocks and re.fullmatch(r"\d{1,3}", blocks[-1].text):
            page_no = int(blocks[-1].text)
            blocks = blocks[:-1]
        elif blocks and re.search(r"(\d{1,3})$", blocks[-1].text):
            m = re.search(r"(\d{1,3})$", blocks[-1].text)
            if m and abs(int(m.group(1)) - (idx + 1)) <= 2:
                page_no = int(m.group(1))
        pages.append(
            Page(
                page_number=page_no,
                part=part,
                item_code=item,
                section=ITEM_NAMES.get(item, f"Item {item}" if item else "Cover / Front matter"),
                blocks=blocks,
                html=raw if keep_html else "",
            )
        )
    return pages
