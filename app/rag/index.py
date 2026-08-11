"""
app/rag/index.py
------------------
Lightweight local vector store built on scikit-learn's TF-IDF vectorizer +
cosine similarity.

Why TF-IDF instead of a neural embedding API?
  - Zero cost, zero network dependency: works identically in CI, on a
    free-tier host with no outbound calls, and completely offline.
  - Deterministic and fast to (re)build on every deploy (no model download).
  - For a single-company policy corpus of ~40 pages, TF-IDF + cosine
    similarity retrieves the right section for the vast majority of
    keyword-bearing HR questions ("PTO carryover", "parental leave weeks"),
    which is what our evaluation set measures.
  - The `VectorIndex` interface below is intentionally storage-agnostic: it
    exposes `add(chunks)`, `search(query, k)`, `save(path)`, `load(path)`.
    Swapping in FAISS + a sentence-transformers/OpenAI embedding model only
    requires reimplementing this one class; nothing else in the RAG/agent/
    MCP layers needs to change. That swap is documented as a "future work"
    item in design-and-evaluation.md.
"""
from __future__ import annotations

import pickle
from dataclasses import asdict
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .chunking import Chunk


class VectorIndex:
    def __init__(self):
        # ngram_range=(1,2) captures short HR phrases ("sick leave", "home
        # office") that unigrams alone would miss; sublinear_tf dampens the
        # effect of very frequent boilerplate terms like "Solarium".
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True,
            stop_words="english",
            max_df=0.9,
        )
        self.matrix = None
        self.chunks: list[Chunk] = []

    def build(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        texts = [f"{c.section}. {c.text}" for c in chunks]
        self.matrix = self.vectorizer.fit_transform(texts)

    def search(self, query: str, k: int = 5, doc_id_filter: str | None = None) -> list[dict]:
        """Top-k retrieval with optional exact doc_id filtering.

        Returns a list of result dicts (chunk metadata + similarity score),
        ranked descending by cosine similarity. `doc_id_filter` supports the
        agent narrowing a follow-up question to a single already-cited
        policy document.
        """
        if self.matrix is None or not self.chunks:
            return []
        q_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self.matrix).flatten()

        ranked_idx = sims.argsort()[::-1]
        results = []
        for i in ranked_idx:
            if doc_id_filter and self.chunks[i].doc_id != doc_id_filter:
                continue
            score = float(sims[i])
            if score <= 0.0:
                continue
            c = self.chunks[i]
            results.append({
                "chunk_id": c.chunk_id,
                "doc_id": c.doc_id,
                "doc_title": c.doc_title,
                "section": c.section,
                "source_format": c.source_format,
                "snippet": _snippet(c.text),
                "text": c.text,
                "score": round(score, 4),
            })
            if len(results) >= k:
                break
        return results

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "vectorizer": self.vectorizer,
                "matrix": self.matrix,
                "chunks": [asdict(c) for c in self.chunks],
            }, f)

    @classmethod
    def load(cls, path: str | Path) -> "VectorIndex":
        with open(path, "rb") as f:
            data = pickle.load(f)
        idx = cls()
        idx.vectorizer = data["vectorizer"]
        idx.matrix = data["matrix"]
        idx.chunks = [Chunk(**c) for c in data["chunks"]]
        return idx


def _snippet(text: str, max_chars: int = 260) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"
