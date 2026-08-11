"""
app/rag/retrieve.py
---------------------
Retrieval orchestration layer sitting on top of VectorIndex: adds a cheap
lexical reranking pass and a "multi-document expansion" helper used for
questions that legitimately span more than one policy (e.g. "If I take
parental leave, does the holiday during that leave get paid, and does it
affect my PTO carryover cap?" touches SOL-HR-101 *and* SOL-HR-102).
"""
from __future__ import annotations

import re
from pathlib import Path

from .index import VectorIndex

_DEFAULT_INDEX_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "rag_index.pkl"

_STOPWORDS = {"the", "a", "an", "is", "are", "do", "does", "of", "to", "for", "and", "or", "my", "i"}


def _keyword_overlap_boost(query: str, text: str) -> float:
    """Small lexical boost so exact keyword matches (e.g. a specific policy
    term like 'bereavement') outrank looser TF-IDF neighbors. This acts as a
    lightweight reranker on top of the cosine-similarity ranking."""
    q_terms = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in _STOPWORDS}
    t_terms = set(re.findall(r"[a-z0-9]+", text.lower()))
    if not q_terms:
        return 0.0
    overlap = len(q_terms & t_terms)
    return overlap / len(q_terms)


class Retriever:
    def __init__(self, index: VectorIndex | None = None, index_path: str | Path = _DEFAULT_INDEX_PATH):
        self.index_path = Path(index_path)
        self.index = index or self._load_or_none()

    def _load_or_none(self) -> VectorIndex | None:
        if self.index_path.exists():
            return VectorIndex.load(self.index_path)
        return None

    def is_ready(self) -> bool:
        return self.index is not None and self.index.matrix is not None

    def search(self, query: str, k: int = 5, doc_id_filter: str | None = None,
               rerank: bool = True) -> list[dict]:
        """Top-k retrieval with optional lexical reranking (see module docstring)."""
        if not self.is_ready():
            return []
        # Retrieve a slightly larger candidate pool than k so reranking has
        # something to work with.
        candidates = self.index.search(query, k=max(k * 3, k), doc_id_filter=doc_id_filter)
        if rerank:
            for r in candidates:
                boost = _keyword_overlap_boost(query, r["text"])
                r["rerank_score"] = round(0.7 * r["score"] + 0.3 * boost, 4)
            candidates.sort(key=lambda r: r["rerank_score"], reverse=True)
        return candidates[:k]

    def document_ids_covered(self, results: list[dict]) -> list[str]:
        seen, ordered = set(), []
        for r in results:
            if r["doc_id"] not in seen:
                seen.add(r["doc_id"])
                ordered.append(r["doc_id"])
        return ordered
