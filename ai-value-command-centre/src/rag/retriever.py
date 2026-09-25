"""Retrieval over the public HPE corpus with metadata filtering and source attribution.

TF-IDF (word 1-2 grams, sublinear tf) keeps the prototype dependency-light and deterministic. The interface
(`search(query, k, filters)` -> passages with url/date/doc) is the same one a pgvector or managed vector store would
implement in an enterprise deployment.
"""
from __future__ import annotations

import re
from functools import lru_cache

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.rag.corpus import load_chunks

MIN_SCORE = 0.06
TOPIC_HINTS = {  # used by the research agent to choose a metadata filter
    "financials": r"revenue|profit|margin|earnings|cash|eps|segment|guidance|results",
    "private cloud ai": r"private cloud ai|pcai|ai factory",
    "greenlake": r"greenlake|arr|run-rate|as-a-service|opsramp",
    "juniper": r"juniper|mist|networking acquisition",
    "nvidia": r"nvidia",
    "sustainability": r"sustainab|energy|emission|living progress|cooling",
    "risk": r"risk factor|risks",
    "supercomputing": r"cray|supercomput|exascale|top500",
    "storage": r"alletra|storage",
}


class Retriever:
    def __init__(self, chunks: list[dict] | None = None):
        self.chunks = chunks if chunks is not None else load_chunks()
        texts = [f"{c['title']} {c['topic']} {c['text']}" for c in self.chunks]
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", min_df=1)
        self.matrix = self.vec.fit_transform(texts) if texts else None

    def search(self, query: str, k: int = 4, topic: str | None = None, source_type: str | None = None,
               date_from: str | None = None) -> list[dict]:
        if self.matrix is None or not query.strip():
            return []
        scores = cosine_similarity(self.vec.transform([query]), self.matrix).ravel()
        mask = np.ones(len(self.chunks), dtype=bool)
        for i, c in enumerate(self.chunks):
            if topic and topic.lower() not in f"{c['topic']} {c['title']}".lower():
                mask[i] = False
            if source_type and source_type.lower() not in str(c["source_type"]).lower():
                mask[i] = False
            if date_from and str(c.get("date") or "") < date_from:
                mask[i] = False
        scores = np.where(mask, scores, -1)
        out, seen_docs = [], {}
        for i in np.argsort(-scores):
            if scores[i] < MIN_SCORE or len(out) >= k:
                break
            c = self.chunks[i]
            if seen_docs.get(c["doc_id"], 0) >= 2:  # diversity: at most two passages per document
                continue
            seen_docs[c["doc_id"]] = seen_docs.get(c["doc_id"], 0) + 1
            out.append({**c, "score": round(float(scores[i]), 4), "citation": len(out) + 1})
        return out

    @staticmethod
    def best_sentences(passage: str, query: str, n: int = 2) -> list[str]:
        sents = [s.strip() for s in re.split(r"(?<=[.!?:])\s+(?=[A-Z\"'(])", passage) if 6 <= len(s.split()) <= 70]
        terms = {w for w in re.findall(r"[a-z0-9$%.]+", query.lower()) if len(w) > 2}
        ranked = sorted(sents, key=lambda s: -len(terms & set(re.findall(r"[a-z0-9$%.]+", s.lower()))))
        return ranked[:n]


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever()
