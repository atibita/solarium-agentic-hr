"""
app/agent/guardrails.py
--------------------------
Safety and grounding guardrails applied before and after retrieval/LLM
generation:

  1. `is_in_scope`          - refuses/redirects clearly out-of-corpus questions
                                (e.g. general programming help, unrelated trivia)
                                instead of letting the LLM improvise an answer.
  2. `has_sufficient_evidence` - blocks the agent from answering a policy
                                question when retrieval confidence is too low,
                                so it says "I don't have that in the policy
                                corpus" instead of hallucinating a plausible-
                                sounding but ungrounded rule.
  3. `requires_confirmation`  - flags MCP tools with side effects
                                (create_mock_hr_ticket, draft_hr_email) so the
                                orchestrator can enforce a confirm-then-act gate,
                                satisfying "prevent irreversible actions."
  4. `label_as_recommendation` - wraps agent-generated advice (as opposed to a
                                directly-quoted policy fact) with a clear label,
                                so users can tell "the policy says X" apart from
                                "given your situation, I'd suggest Y."
"""
from __future__ import annotations

import re

# Topics this agent is scoped to. Anything not touching these (or the
# employee/PTO/benefits/ticket data model) is out of corpus.
IN_SCOPE_KEYWORDS = [
    "pto", "vacation", "leave", "holiday", "sick", "bereavement", "jury",
    "parental", "remote", "hybrid", "work from home", "work model",
    "expense", "reimburs", "travel", "mileage", "corporate card",
    "security", "password", "mfa", "phishing", "data", "device", "vpn",
    "benefit", "health", "dental", "vision", "401", "retirement", "fsa",
    "life insurance", "disability", "wellness",
    "onboarding", "new hire", "training",
    "equipment", "laptop", "monitor", "hardware", "software",
    "conduct", "harassment", "discrimination", "retaliation", "report",
    "manager", "employee", "office", "ticket", "hr", "policy", "solarium",
]

OUT_OF_SCOPE_HINT_PATTERNS = [
    r"\bweather\b", r"\bstock price\b", r"\brecipe\b", r"\btranslate\b",
    r"\bwrite (a|me) (a )?(poem|song|story)\b", r"\bpolitical\b", r"\bmedical diagnosis\b",
]

MIN_RETRIEVAL_SCORE = 0.20  # below this, treat retrieval as "no real evidence"


def is_in_scope(query: str) -> bool:
    q = query.lower()
    if any(re.search(p, q) for p in OUT_OF_SCOPE_HINT_PATTERNS):
        return False
    return any(kw in q for kw in IN_SCOPE_KEYWORDS)


def has_sufficient_evidence(retrieval_results: list[dict], min_score: float = MIN_RETRIEVAL_SCORE) -> bool:
    if not retrieval_results:
        return False
    top_score = retrieval_results[0].get("rerank_score", retrieval_results[0].get("score", 0))
    return top_score >= min_score


ACTION_TOOLS_REQUIRING_CONFIRMATION = {"create_mock_hr_ticket", "draft_hr_email"}


def requires_confirmation(tool_name: str) -> bool:
    return tool_name in ACTION_TOOLS_REQUIRING_CONFIRMATION


def out_of_scope_message() -> str:
    return (
        "That's outside what I can help with — I'm scoped to Solarium HR policy topics "
        "(PTO, holidays, remote work, expenses, data security, benefits, onboarding, "
        "equipment, and workplace conduct) plus your own employee, PTO, and benefits records. "
        "Try rephrasing your question around one of those topics, or contact "
        "people-ops@solarium.example for anything else."
    )


def insufficient_evidence_message(query: str) -> str:
    return (
        "I searched the Solarium policy corpus but didn't find a section that clearly "
        f"answers \u201c{query}\u201d. Rather than guess, I'd recommend checking with "
        "People Operations (people-ops@solarium.example) directly, or rephrasing your "
        "question with more specific policy terms."
    )
