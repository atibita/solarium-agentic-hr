"""
app/rag/ingest.py
-------------------
Builds the local vector index from the policy_corpus/ directory and
persists it to data/rag_index.pkl. Run via `python -m scripts.build_index`
(see scripts/build_index.py) or directly:

    python -m app.rag.ingest

This is re-run automatically on deploy (see README "Deployment" section) so
the index always reflects whatever is currently committed under
policy_corpus/. Chunking uses fixed parameters (see chunking.py) so the
index is byte-for-byte reproducible given the same corpus -- there is no
random sampling in this step, satisfying the "fixed seeds where applicable"
reproducibility requirement.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.loaders import load_corpus          # noqa: E402
from app.rag.chunking import chunk_corpus         # noqa: E402
from app.rag.index import VectorIndex             # noqa: E402

CORPUS_DIR = PROJECT_ROOT / "policy_corpus"
INDEX_PATH = PROJECT_ROOT / "data" / "rag_index.pkl"


def build_index(corpus_dir: Path = CORPUS_DIR, index_path: Path = INDEX_PATH,
                 max_words: int = 220, overlap_words: int = 40) -> VectorIndex:
    t0 = time.time()
    docs = load_corpus(corpus_dir)
    if not docs:
        raise RuntimeError(f"No supported policy documents found in {corpus_dir}")

    chunks = chunk_corpus(docs, max_words=max_words, overlap_words=overlap_words)

    index = VectorIndex()
    index.build(chunks)
    index.save(index_path)

    elapsed = time.time() - t0
    print(f"[rag.ingest] Indexed {len(docs)} documents into {len(chunks)} chunks "
          f"in {elapsed:.2f}s -> {index_path}")
    for d in docs:
        n = sum(1 for c in chunks if c.doc_id == d.doc_id)
        print(f"  - {d.doc_id:<14} {d.source_format:<9} {n:>3} chunks  {d.title}")
    return index


if __name__ == "__main__":
    build_index()
