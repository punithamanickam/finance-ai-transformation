"""Public HPE document corpus: markdown source cards -> metadata-tagged chunks.

Each file in data/public/hpe_documents/ starts with a front-matter block:

    ---
    doc_id: hpe-10k-fy2025
    title: ...
    url: https://...
    date: 2025-12-18
    topic: financials
    source_type: 10-K
    ---
"""
from __future__ import annotations

import re

from src import settings

CHUNK_WORDS = 140
OVERLAP_WORDS = 30


def parse_document(raw: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
    if not m:
        return {}, raw
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, m.group(2)


def clean_markdown(body: str) -> str:
    """Plain text for retrieval and display: headings become sentences, emphasis and quote markers are removed."""
    lines = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#"):
            s = s.lstrip("#").strip()
            s = s + "." if s and not s.endswith((".", ":", "?")) else s
        s = re.sub(r"^>\s?", "", s)
        s = re.sub(r"^[-*]\s+", "", s)
        s = s.replace("**", "").replace("__", "")
        lines.append(s)
    return "\n".join(lines)


def chunk_text(body: str, size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    body = clean_markdown(body)
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks, cur = [], []
    for p in paras:
        words = p.split()
        if cur and len(cur) + len(words) > size:
            chunks.append(" ".join(cur))
            cur = cur[-overlap:] if overlap else []
        cur.extend(words)
        while len(cur) > size * 1.6:
            chunks.append(" ".join(cur[:size]))
            cur = cur[size - overlap:]
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def load_chunks() -> list[dict]:
    out = []
    if not settings.HPE_DOCS_DIR.exists():
        return out
    for path in sorted(settings.HPE_DOCS_DIR.glob("*.md")):
        meta, body = parse_document(path.read_text())
        if not meta.get("url"):
            continue  # un-attributable text never enters the corpus
        doc_id = meta.get("doc_id", path.stem)
        for i, text in enumerate(chunk_text(body)):
            out.append({"chunk_id": f"{doc_id}#{i}", "doc_id": doc_id, "title": meta.get("title", path.stem),
                        "url": meta["url"], "date": meta.get("date"), "topic": meta.get("topic", "general"),
                        "source_type": meta.get("source_type", "web"), "text": text})
    return out
