"""
mcp_server/tools/policy_tools.py
-----------------------------------
MCP tools backed by the RAG index. These are the tools whose results ground
the agent's final answer and produce citations.

Tools defined here:
  - search_policy_documents : top-k semantic + lexical search over the corpus
  - get_policy_section       : fetch a specific section's full text (used
                                 when the agent needs the complete rule, not
                                 just a snippet, e.g. reading an entire table)
  - check_policy_compliance  : a light rules-engine style check that
                                 combines a retrieved policy rule with a
                                 numeric fact (e.g. "expense amount") to
                                 return a compliant/non-compliant verdict
"""
from __future__ import annotations

from app.rag.retrieve import Retriever

_retriever: Retriever | None = None


def _get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def search_policy_documents(query: str, k: int = 5, doc_id: str | None = None) -> dict:
    """Semantic + lexical search over the Solarium policy corpus.

    Args:
        query: natural-language question or keywords
        k: number of results to return (default 5)
        doc_id: optional exact policy Document ID to restrict the search to
                 (e.g. "SOL-HR-101"), used for follow-up questions
    """
    retriever = _get_retriever()
    if not retriever.is_ready():
        raise RuntimeError(
            "RAG index is not built yet. Run `python -m app.rag.ingest` "
            "(see README 'Local Run' section) before starting the server."
        )
    results = retriever.search(query, k=k, doc_id_filter=doc_id)
    return {
        "query": query,
        "result_count": len(results),
        "documents_covered": retriever.document_ids_covered(results),
        "results": [
            {
                "doc_id": r["doc_id"],
                "doc_title": r["doc_title"],
                "section": r["section"],
                "snippet": r["snippet"],
                "score": r["rerank_score"],
            }
            for r in results
        ],
    }


def get_policy_section(document_id: str, section: str) -> dict:
    """Fetch the full text of a specific section of a specific policy
    document (exact or fuzzy section title match).

    Args:
        document_id: canonical Document ID, e.g. "SOL-HR-101"
        section: section title or a substring of it, e.g. "Bereavement"
    """
    retriever = _get_retriever()
    if not retriever.is_ready():
        raise RuntimeError("RAG index is not built yet.")

    section_lower = section.lower()
    matches = [
        c for c in retriever.index.chunks
        if c.doc_id == document_id and section_lower in c.section.lower()
    ]
    if not matches:
        # Fall back to a semantic search scoped to the document so a
        # slightly-off section name (e.g. "vacation" instead of "PTO
        # accrual") still returns something useful instead of a hard miss.
        fallback = retriever.search(section, k=1, doc_id_filter=document_id)
        if not fallback:
            return {
                "document_id": document_id, "section": section,
                "found": False,
                "message": f"No section matching '{section}' found in {document_id}.",
            }
        best = fallback[0]
        return {
            "document_id": document_id, "section": best["section"],
            "found": True, "text": best["text"], "matched_via": "semantic_fallback",
        }

    combined_text = "\n\n".join(m.text for m in matches)
    return {
        "document_id": document_id,
        "section": matches[0].section,
        "found": True,
        "text": combined_text,
        "matched_via": "exact_or_substring",
    }


def check_policy_compliance(topic: str, amount: float | None = None,
                             context: str | None = None) -> dict:
    """Check a proposed action against retrieved policy rules for a topic
    (currently tuned for expense-amount compliance checks; generalizes to
    any topic by retrieving the relevant rule and returning it alongside a
    best-effort verdict the agent can present with appropriate hedging).

    Args:
        topic: what to check, e.g. "client meal expense" or "business class flight"
        amount: optional dollar amount to check against a stated cap
        context: optional extra context, e.g. "traveling internationally"
    """
    retriever = _get_retriever()
    if not retriever.is_ready():
        raise RuntimeError("RAG index is not built yet.")

    query = f"{topic} policy limit rule {context or ''}".strip()
    results = retriever.search(query, k=3)
    if not results:
        return {
            "topic": topic, "amount": amount, "verdict": "unknown",
            "reason": "No relevant policy text was found for this topic in the corpus.",
            "evidence": [],
        }

    top = results[0]
    verdict = "needs_human_review"
    reason = ("A relevant policy section was found, but automatic amount-vs-cap "
              "comparison is only implemented for a few well-known caps; the agent "
              "should quote the retrieved rule rather than assert a verdict on its own.")

    # A couple of well-known, explicitly documented numeric caps we can
    # safely automate; anything else stays "needs_human_review" rather than
    # guessing, per the "limit unsupported claims" guardrail requirement.
    known_caps = {
        "meal": 75.0,          # SOL-FIN-301 daily travel meal cap
        "ergonomic": 300.0,    # SOL-OPS-202 ergonomic equipment cap
        "professional development": 1000.0,  # SOL-HR-103 annual cap
    }
    for keyword, cap in known_caps.items():
        if keyword in topic.lower() and amount is not None:
            verdict = "within_policy" if amount <= cap else "exceeds_policy_cap"
            reason = f"Compared ${amount:.2f} against the documented cap of ${cap:.2f}."
            break

    return {
        "topic": topic,
        "amount": amount,
        "verdict": verdict,
        "reason": reason,
        "evidence": [
            {"doc_id": r["doc_id"], "section": r["section"], "snippet": r["snippet"]}
            for r in results
        ],
    }
