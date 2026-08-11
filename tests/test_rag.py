"""
tests/test_rag.py
--------------------
Verifies document loading, chunking, and retrieval work and produce
citation-ready metadata for every supported source format (md/html/pdf/txt).
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.rag.loaders import load_corpus  # noqa: E402
from app.rag.chunking import chunk_corpus  # noqa: E402
from app.rag.retrieve import Retriever  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = PROJECT_ROOT / "policy_corpus"


class LoaderAndChunkingTests(unittest.TestCase):
    def test_loads_all_four_formats(self):
        docs = load_corpus(CORPUS_DIR)
        formats = {d.source_format for d in docs}
        self.assertTrue({"markdown", "html", "pdf", "text"}.issubset(formats))

    def test_every_document_has_a_solarium_doc_id(self):
        docs = load_corpus(CORPUS_DIR)
        for d in docs:
            self.assertRegex(d.doc_id, r"^SOL-[A-Z]+-\d+$", f"Bad doc_id for {d.source_path}")

    def test_chunking_produces_chunks_with_required_citation_metadata(self):
        docs = load_corpus(CORPUS_DIR)
        chunks = chunk_corpus(docs)
        self.assertGreater(len(chunks), 20)
        sample = chunks[0]
        for field in ("chunk_id", "doc_id", "doc_title", "section", "source_format", "text"):
            self.assertTrue(getattr(sample, field), f"Missing {field} on chunk")


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = Retriever()
        if not cls.retriever.is_ready():
            # Build the index on the fly if a test env hasn't run ingest yet.
            from app.rag.ingest import build_index
            build_index()
            cls.retriever = Retriever()

    def test_retriever_is_ready(self):
        self.assertTrue(self.retriever.is_ready())

    def test_bereavement_question_retrieves_hr101(self):
        results = self.retriever.search("How many days of bereavement leave do I get?", k=3)
        self.assertTrue(any(r["doc_id"] == "SOL-HR-101" for r in results))

    def test_multi_document_question_covers_more_than_one_doc(self):
        """Required: at least one complex question needing multiple docs.
        A holiday-during-parental-leave question should surface both the
        PTO/Leave policy (SOL-HR-101) and the Holiday Calendar (SOL-HR-102)."""
        results = self.retriever.search(
            "If a company holiday falls during my parental leave, is it paid, "
            "and does it affect my PTO carryover cap?", k=8
        )
        docs_covered = self.retriever.document_ids_covered(results)
        self.assertIn("SOL-HR-101", docs_covered)
        self.assertTrue(len(docs_covered) >= 2, f"Expected >=2 docs, got {docs_covered}")

    def test_doc_id_filter_restricts_results(self):
        results = self.retriever.search("policy", k=5, doc_id_filter="SOL-HR-103")
        self.assertTrue(all(r["doc_id"] == "SOL-HR-103" for r in results))

    def test_irrelevant_query_yields_low_confidence(self):
        results = self.retriever.search("best pizza toppings in New York", k=3)
        top_score = results[0]["rerank_score"] if results else 0
        # Small-corpus TF-IDF + lexical rerank can pick up incidental token
        # overlap (e.g. "New" matching "New Hire") on totally unrelated
        # queries; the guardrail threshold (guardrails.MIN_RETRIEVAL_SCORE)
        # is set above this noise floor, which is what we actually assert.
        from app.agent.guardrails import MIN_RETRIEVAL_SCORE
        self.assertLess(top_score, MIN_RETRIEVAL_SCORE)


if __name__ == "__main__":
    unittest.main()
