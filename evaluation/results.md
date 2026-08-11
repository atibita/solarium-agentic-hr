# Evaluation Results

This file is a human-readable narrative of a `python -m evaluation.run_eval` run.
The machine-readable version (regenerated on every run) is `results.json`. All
numbers below are from an actual run against the in-process agent with the
offline (no-LLM) template synthesizer, so anyone can reproduce them exactly
with zero API cost by running the same command.

## How to reproduce

```bash
python -m app.rag.ingest        # build the RAG index (idempotent, deterministic)
python -m evaluation.run_eval    # run all 26 eval questions + the ablation
```

## Evaluation set

26 questions/tasks in `eval_questions.json` across 6 categories:

| Category | Count | What it tests |
|---|---|---|
| `policy_qa` | 14 | Straightforward single-document policy questions with a gold answer |
| `multi_document` | 1 | A question that legitimately requires evidence from 2+ policy documents |
| `tool_required` | 6 | Questions that require an MCP tool call (PTO/benefits/profile lookup, compliance check, or a multi-step workflow) |
| `ambiguous` | 2 | Underspecified requests that should trigger a clarification, not a guess |
| `out_of_scope` | 2 | Questions unrelated to Solarium HR policy, which should be declined |
| `action_confirmation` | 1 | A request for an irreversible mock action (ticket creation), which must be gated behind explicit confirmation |

## Results summary (most recent run)

| Metric | Result |
|---|---|
| Groundedness rate (policy answers cite >=1 source) | **100%** (15/15 applicable questions) |
| Citation accuracy (expected Document ID actually cited) | **100%** |
| Multi-document coverage (>=2 docs cited on Q15) | **Pass** — cited SOL-HR-101, SOL-HR-102, and SOL-HR-999 |
| Tool selection accuracy (expected MCP tool(s) actually called) | **100%** (6/6 tool-required questions) |
| Escalation/clarification accuracy (ambiguous requests correctly ask for clarification) | **100%** (2/2) |
| Out-of-scope refusal rate | **100%** (2/2) |
| Action-safety pass rate (action tool NOT called before confirmation) | **100%** (1/1) |
| Action executes correctly once confirmed | **100%** (1/1) |
| Workflow completion rate (no unhandled `action_error`) | **100%** (26/26) |
| Latency p50 | **1.77 ms** (in-process transport, offline synthesis, local dev machine) |
| Latency p95 | **2.91 ms** |
| Latency mean | **1.71 ms** |

**Reading the latency numbers:** these are in-process/offline-synthesis
numbers on a local dev machine — they mainly demonstrate that RAG
retrieval + rule-based orchestration + mock-data lookups are all fast
(single-digit milliseconds; TF-IDF search over ~100 chunks and dict lookups
over ~40 mock employee records are both essentially free). **They do not
include LLM API latency** (typically 500ms-3s per call when an LLM is
configured) **or free-tier cold-start latency**, both of which dominate
real-world response time. See "Cold start vs. warm latency" below and
`Deployed.md` for the honest, deployment-realistic numbers.

## Cold start vs. warm latency (free-tier deployment)

Render/Railway free-tier web services spin down after a period of
inactivity and take roughly **30-60 seconds** to cold-start on the next
request (documented in `Deployed.md`). Once warm:
- With `LLM_API_KEY` unset (offline template synthesis): expect low
  single-digit-to-tens-of-milliseconds server-side processing per `/chat`
  call, as measured above, plus normal network round-trip time.
- With an LLM configured: expect roughly **1-3 seconds** per `/chat` call,
  dominated by the LLM completion call, not by retrieval or tool calls.

If deploying the MCP server as a **separate** free-tier service (HTTP
transport), add one more cold start (the MCP service) and roughly
5-20ms of HTTP round-trip per tool call once both services are warm — see
the HTTP-transport unit tests in `tests/test_mcp_tools.py`, which measure
this directly against a live local server and stay in the same
single-digit-millisecond range.

## Ablation: retrieval `k` value

Run on the required multi-document evaluation question (holiday-during-
parental-leave + PTO carryover). `k` = number of candidate chunks requested
before reranking and truncation to the final top-k shown to the LLM/template.

| k | Unique documents covered | Documents | Mean rerank score |
|---|---|---|---|
| 3  | 3 | SOL-HR-102, SOL-HR-999, SOL-HR-101 | 0.2843 |
| 5  | 3 | SOL-HR-102, SOL-HR-999, SOL-HR-101 | 0.2566 |
| 8  | 3 | SOL-HR-102, SOL-HR-999, SOL-HR-101 | 0.2289 |
| 12 | 3 | SOL-HR-102, SOL-HR-999, SOL-HR-101 | 0.2053 |

**Takeaway:** for this corpus size (~100 chunks across 11 documents), `k=3`
already surfaces every document relevant to the multi-document question,
and mean relevance score *decreases* as `k` grows (expected — later results
are, by definition, less relevant). We ship the default `k=5` used
throughout the orchestrator (see `orchestrator.py`) as a balance between
giving the LLM/template enough supporting snippets to write a complete
answer and not diluting the prompt with low-relevance chunks. For a larger
corpus (hundreds of documents), we'd expect the optimal k to grow and would
re-run this ablation before changing the default.

## Known limitations surfaced by evaluation

- **TF-IDF lexical noise on unrelated queries.** A nonsense/off-topic query
  can occasionally produce a nonzero top score due to incidental token
  overlap (e.g., "New York" partially matching "New Hire" in the onboarding
  guide). The out-of-scope guardrail's minimum-score threshold
  (`guardrails.MIN_RETRIEVAL_SCORE = 0.20`) was tuned with this in mind and
  the eval set's out-of-scope questions (Q24/Q25) still pass because they're
  caught earlier by keyword-based scope detection, not retrieval score alone
  — but a determined adversarial query could probably find a gap. A neural
  embedding model (see `app/rag/index.py` docstring for the swap-in plan)
  would likely reduce, though not eliminate, this class of false positive.
- **Rule-based intent classification is keyword-driven**, so phrasings far
  from the patterns in `orchestrator.classify_intent()` can fall through to
  the generic `policy_qa` handler instead of a more specific workflow. This
  still produces a grounded, cited answer (as seen when
  `test_multi_step_workflow_pto_request_guidance` initially misclassified a
  paraphrased PTO request before the keyword list was broadened) — it just
  means the more specialized multi-step workflow (e.g., combining a live PTO
  balance) doesn't always trigger on the first try.
