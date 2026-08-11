"""
evaluation/run_eval.py
-------------------------
Runs evaluation/eval_questions.json against the agent orchestrator (in-
process transport, offline LLM mode by default so this is reproducible with
zero API cost) and reports:

  - Answer quality: groundedness (citations present when expected),
    citation accuracy (expected doc IDs actually cited)
  - Agent behavior: tool selection accuracy, workflow completion rate,
    escalation/clarification accuracy, action-safety pass rate
  - System: latency p50/p95 across all questions
  - An ablation: retrieval k=3 vs k=5 vs k=8 on the multi-document question

Usage:
    python -m evaluation.run_eval

Writes evaluation/results.json (machine-readable) and prints a human
summary; results.md is a hand-written narrative of a prior run kept in the
repo for readability without needing to re-run the script.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.orchestrator import AgentOrchestrator  # noqa: E402
from app.rag.retrieve import Retriever  # noqa: E402

EVAL_PATH = Path(__file__).resolve().parent / "eval_questions.json"
RESULTS_PATH = Path(__file__).resolve().parent / "results.json"


def run_eval() -> dict:
    with open(EVAL_PATH) as f:
        eval_set = json.load(f)

    agent = AgentOrchestrator()
    per_question = []
    latencies = []

    for q in eval_set["questions"]:
        t0 = time.time()
        resp = agent.handle(q["question"], employee_id=q.get("employee_id"))
        latency_ms = (time.time() - t0) * 1000
        latencies.append(latency_ms)

        cited_docs = {c["doc_id"] for c in resp.citations}
        called_tools = {s["tool_name"] for s in resp.trace if s.get("tool_name")}

        result = {
            "id": q["id"], "category": q["category"], "question": q["question"],
            "workflow": resp.workflow, "latency_ms": round(latency_ms, 2),
            "cited_docs": sorted(cited_docs), "called_tools": sorted(called_tools),
            "clarification_needed": resp.clarification_needed,
            "pending_action": bool(resp.pending_action),
            "answer_preview": resp.answer[:180],
        }

        # -- per-category pass/fail scoring --
        if q["category"] == "policy_qa":
            expected = set(q.get("expected_doc_ids", []))
            result["groundedness_pass"] = bool(cited_docs)
            result["citation_accuracy_pass"] = expected.issubset(cited_docs) if expected else bool(cited_docs)
        elif q["category"] == "multi_document":
            expected = set(q.get("expected_doc_ids", []))
            result["groundedness_pass"] = bool(cited_docs)
            result["citation_accuracy_pass"] = expected.issubset(cited_docs)
            result["multi_doc_pass"] = len(cited_docs) >= 2
        elif q["category"] == "tool_required":
            expected_tools = set(q.get("expected_tools", []))
            result["tool_selection_pass"] = expected_tools.issubset(called_tools)
        elif q["category"] == "ambiguous":
            result["escalation_pass"] = resp.clarification_needed
        elif q["category"] == "out_of_scope":
            result["out_of_scope_pass"] = resp.workflow == "out_of_scope"
        elif q["category"] == "action_confirmation":
            # action-safety: the action tool must NOT be in the trace on
            # the first turn -- only a pending_action should be returned.
            action_tools = {"create_mock_hr_ticket", "draft_hr_email"}
            result["action_safety_pass"] = bool(resp.pending_action) and not (called_tools & action_tools)
            # then verify confirming actually executes it
            confirmed = agent.handle("", confirm=True, pending_action=resp.pending_action)
            confirmed_tools = {s["tool_name"] for s in confirmed.trace if s.get("tool_name")}
            result["action_confirmation_executes_pass"] = bool(confirmed_tools & action_tools)

        per_question.append(result)

    summary = _summarize(per_question, latencies)
    ablation = run_ablation()

    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "question_count": len(per_question),
        "summary": summary,
        "ablation": ablation,
        "per_question": per_question,
    }
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2)

    _print_summary(summary, ablation)
    return output


def _summarize(results: list[dict], latencies: list[float]) -> dict:
    def rate(key):
        vals = [r[key] for r in results if key in r]
        return round(sum(vals) / len(vals), 3) if vals else None

    latencies_sorted = sorted(latencies)
    p50 = statistics.median(latencies_sorted)
    p95_idx = min(int(round(0.95 * (len(latencies_sorted) - 1))), len(latencies_sorted) - 1)
    p95 = latencies_sorted[p95_idx]

    return {
        "groundedness_rate": rate("groundedness_pass"),
        "citation_accuracy_rate": rate("citation_accuracy_pass"),
        "multi_doc_rate": rate("multi_doc_pass"),
        "tool_selection_accuracy": rate("tool_selection_pass"),
        "escalation_clarification_accuracy": rate("escalation_pass"),
        "out_of_scope_refusal_rate": rate("out_of_scope_pass"),
        "action_safety_pass_rate": rate("action_safety_pass"),
        "action_confirmation_executes_rate": rate("action_confirmation_executes_pass"),
        "workflow_completion_rate": round(
            sum(1 for r in results if r["workflow"] not in ("action_error",)) / len(results), 3
        ),
        "latency_ms_p50": round(p50, 2),
        "latency_ms_p95": round(p95, 2),
        "latency_ms_mean": round(statistics.mean(latencies), 2),
    }


def run_ablation() -> dict:
    """Ablation: retrieval k value vs. multi-document coverage + mean score,
    on the required multi-document evaluation question."""
    retriever = Retriever()
    query = ("If a company holiday falls during my approved parental leave, is it paid, and "
             "separately, does taking that leave affect how many PTO days I can carry over into next year?")
    rows = []
    for k in (3, 5, 8, 12):
        results = retriever.search(query, k=k)
        docs = retriever.document_ids_covered(results)
        mean_score = round(statistics.mean(r["rerank_score"] for r in results), 4) if results else 0.0
        rows.append({"k": k, "result_count": len(results), "documents_covered": docs,
                      "unique_doc_count": len(docs), "mean_rerank_score": mean_score})
    return {"dimension": "retrieval_k", "query": query, "rows": rows}


def _print_summary(summary: dict, ablation: dict):
    print("=== Solarium HR Assistant -- Evaluation Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print("\n=== Ablation: retrieval k value (multi-document question) ===")
    for row in ablation["rows"]:
        print(f"  k={row['k']:<3} docs_covered={row['unique_doc_count']} "
              f"{row['documents_covered']} mean_score={row['mean_rerank_score']}")


if __name__ == "__main__":
    run_eval()
