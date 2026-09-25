"""Lightweight semantic retrieval.

Default embedder: TF-IDF (word 1-2 grams, sublinear TF) with cosine similarity - deterministic, offline and
fast enough for a single 10-K corpus. The ``Embedder`` protocol lets a dense embedding model plus FAISS /
Chroma / pgvector replace it without touching the copilot.
"""
from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from src import settings
from src.retrieval.chunker import Chunk, read_chunks

FINANCE_SYNONYMS = {
    r"\bcapex\b": "capital expenditures additions to property and equipment",
    r"\br&d\b": "research and development",
    r"\bs&m\b": "sales and marketing",
    r"\bg&a\b": "general and administrative",
    r"\bfcf\b": "free cash flow",
    r"\bopex\b": "operating expenses",
    r"\bai\b": "AI artificial intelligence",
    r"\bfx\b": "foreign currency exchange",
}


def expand_query(q: str) -> str:
    out = q
    for pat, rep in FINANCE_SYNONYMS.items():
        if re.search(pat, q, re.IGNORECASE):
            out += " " + rep
    return out


class Embedder(Protocol):
    def fit(self, texts: list[str]) -> None: ...
    def encode(self, texts: list[str]): ...


class TfidfEmbedder:
    name = "tfidf-1-2gram-sublinear"

    def __init__(self):
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", min_df=1, max_df=0.6)

    def fit(self, texts):
        self.vec.fit(texts)

    def encode(self, texts):
        return self.vec.transform(texts)


@dataclass
class Hit:
    chunk: Chunk
    score: float

    def citation(self) -> str:
        c = self.chunk
        return f"{c.document}, {c.section}{' - ' + c.heading if c.heading else ''}, page {c.page}"


class VectorStore:
    def __init__(self, chunks: list[Chunk], embedder: Embedder | None = None):
        self.chunks = chunks
        self.embedder = embedder or TfidfEmbedder()
        texts = [f"{c.heading} {c.text}" for c in chunks]
        if texts:
            self.embedder.fit(texts)
            self.matrix = self.embedder.encode(texts)
        else:
            self.matrix = None

    def search(self, query: str, k: int = 5, content_types: set[str] | None = None, min_score: float = 0.05,
               source_ids: set[str] | None = None) -> list[Hit]:
        if self.matrix is None:
            return []
        qv = self.embedder.encode([expand_query(query)])
        scores = (self.matrix @ qv.T).toarray().ravel()
        order = np.argsort(-scores)
        hits: list[Hit] = []
        for i in order:
            if scores[i] < min_score:
                break
            c = self.chunks[i]
            if content_types and c.content_type not in content_types:
                continue
            if source_ids and c.source_id not in source_ids:
                continue
            hits.append(Hit(c, float(scores[i])))
            if len(hits) >= k:
                break
        return hits


def build_index(chunks: list[Chunk] | None = None) -> VectorStore:
    store = VectorStore(chunks if chunks is not None else read_chunks())
    with open(settings.INDEX_PATH, "wb") as f:
        pickle.dump(store, f)
    return store


_STORE: VectorStore | None = None


def get_store() -> VectorStore:
    global _STORE
    if _STORE is None:
        if settings.INDEX_PATH.exists():
            with open(settings.INDEX_PATH, "rb") as f:
                _STORE = pickle.load(f)
        else:
            _STORE = VectorStore(read_chunks())
    return _STORE


def retrieval_available() -> bool:
    return bool(get_store().chunks)
