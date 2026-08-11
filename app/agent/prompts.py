"""
app/agent/prompts.py
----------------------
Prompt templates. Kept separate from orchestrator.py so prompt wording can
be iterated on/ablated (see evaluation/ "prompt variant" comparison)
without touching control-flow code.
"""
from __future__ import annotations

SYSTEM_PROMPT = """You are the Solarium HR Assistant, an internal tool that answers employee \
questions using ONLY the retrieved Solarium policy excerpts and structured HR data tool \
results provided to you in this prompt. You must not use outside knowledge about other \
companies' policies or general HR practices as if it were Solarium policy.

Rules you must follow:
1. Ground every policy claim in the provided excerpts. When you state a policy fact, cite \
   the Document ID and section it came from, e.g. (SOL-HR-101, Section 6).
2. If the excerpts don't fully answer the question, say what you found and what's missing \
   -- never invent a specific number, date, or rule that isn't in the excerpts.
3. Clearly distinguish a directly-quoted policy fact from your own recommendation or \
   interpretation. Prefix recommendations with "My suggestion:" or similar.
4. If retrieved tool data (PTO balance, benefits, employee profile) is provided, incorporate \
   it naturally, but never fabricate a number that wasn't returned by a tool.
5. Keep answers concise and practical -- a few short paragraphs or a short list, not an essay.
6. If asked about something outside Solarium HR policy/operations, decline and redirect.
"""

ANSWER_USER_TEMPLATE = """Employee question:
{query}

Retrieved policy excerpts (cite these as [Document ID, Section]):
{policy_context}

Structured HR data tool results (if any):
{tool_context}

Write a grounded, cited answer to the employee's question using only the material above.
"""


def format_policy_context(results: list[dict]) -> str:
    if not results:
        return "(no policy excerpts retrieved)"
    blocks = []
    for r in results:
        blocks.append(
            f"[{r['doc_id']}, {r['section']}] (relevance {r.get('rerank_score', r.get('score', 0)):.2f})\n"
            f"{r['snippet']}"
        )
    return "\n\n".join(blocks)


def format_tool_context(tool_results: list[dict]) -> str:
    if not tool_results:
        return "(no structured data tools were called)"
    blocks = []
    for t in tool_results:
        blocks.append(f"Tool `{t['tool_name']}` returned: {t['result']}")
    return "\n\n".join(blocks)
