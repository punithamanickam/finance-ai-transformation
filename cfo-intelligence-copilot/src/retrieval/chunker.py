"""Turn parsed filing pages into retrieval chunks that keep document / page / section / heading provenance."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from src import settings
from src.ingestion.document_parser import Page
from src.ingestion.source_registry import load_registry

MAX_CHARS = 1100


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    document: str
    source_url: str
    page: int
    section: str
    heading: str
    kind: str  # paragraph | table
    content_type: str  # management_commentary | risk_factor | notes | financial_statement | business | other
    text: str


def classify(source_id: str, item: str, kind: str) -> str:
    if source_id.startswith("MSFT-8K"):
        return "management_commentary"
    if item == "7":
        return "management_commentary" if kind == "paragraph" else "financial_statement"
    if item == "7A":
        return "risk_factor"
    if item == "1A":
        return "risk_factor"
    if item == "8":
        return "financial_statement" if kind == "table" else "notes"
    if item in {"1", "1C", "2", "3"}:
        return "business"
    return "other"


def build_chunks(pages: list[Page], source_id: str) -> list[Chunk]:
    reg = load_registry().set_index("source_id")
    doc, url = reg.loc[source_id, "short_name"], reg.loc[source_id, "source_url"]
    chunks: list[Chunk] = []
    for pg in pages:
        if pg.item_code in {"15", "16"} or pg.section.startswith("Cover"):
            continue  # exhibit index / cover add no analytical content
        buf, buf_heading, n = [], None, 0

        def flush():
            nonlocal buf, n
            if buf:
                text = " ".join(buf).strip()
                if len(text) > 60:
                    chunks.append(Chunk(f"{source_id}-p{pg.page_number}-{n}", source_id, doc, url, pg.page_number,
                                        pg.section, buf_heading or "", "paragraph",
                                        classify(source_id, pg.item_code, "paragraph"), text))
                    n += 1
            buf = []

        for b in pg.blocks:
            if b.kind == "heading":
                flush()
                buf_heading = b.heading or b.text
                continue
            if b.kind == "table":
                flush()
                chunks.append(Chunk(f"{source_id}-p{pg.page_number}-{n}", source_id, doc, url, pg.page_number, pg.section,
                                    b.heading, "table", classify(source_id, pg.item_code, "table"), b.text[:2500]))
                n += 1
                continue
            if sum(len(x) for x in buf) + len(b.text) > MAX_CHARS:
                flush()
            buf.append(b.text)
            buf_heading = buf_heading if buf_heading is not None else b.heading
        flush()
    return chunks


def write_chunks(chunks: list[Chunk]) -> None:
    with open(settings.CHUNKS_JSONL, "w") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c)) + "\n")


def read_chunks() -> list[Chunk]:
    if not settings.CHUNKS_JSONL.exists():
        return []
    return [Chunk(**json.loads(line)) for line in settings.CHUNKS_JSONL.read_text().splitlines() if line.strip()]
