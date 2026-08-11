# AI Tooling Notes

This document describes which AI coding tools were used to build the
Solarium HR Assistant, how they were used, and an honest account of what
worked well versus what needed manual correction.

## Tools used

- **Claude (Anthropic), used conversationally as an AI pair-programmer** for
  the entire codebase: architecture design, all Python modules (RAG
  pipeline, MCP tool registry/server, agent orchestrator, Flask app),
  front-end code (HTML/CSS/JS chat UI), tests, evaluation harness, CI/CD
  workflow, and all project documentation (this file, `README.md`,
  `design-and-evaluation.md`, `Deployed.md`).
- **A sandboxed Python execution environment** (bash + Python) driven by
  the same session, used to actually *run* the code as it was written —
  build the RAG index, execute the MCP tool registry, hit the Flask test
  client, and run the full `pytest` suite — rather than generating code
  that was never executed. Every claim in `design-and-evaluation.md` and
  `evaluation/results.md` (chunk counts, test pass counts, latency numbers,
  ablation results) comes from an actual run captured during this process,
  not from hand-estimation.

No other AI coding tools (e.g., GitHub Copilot, Cursor, ChatGPT) were used
for this project — the entire build happened in one continuous AI-assisted
session.

## How it was used

1. **Spec → architecture pass.** The project brief (RAG + agent + MCP +
   web app + deploy + CI + eval, all free-tier) was translated into a
   concrete module layout (`app/`, `mcp_server/`, `evaluation/`, `tests/`)
   before any code was written, so later modules had a stable interface to
   target (e.g., `MCPClient.call_tool()` was designed once and never
   changed shape, even though its two transport implementations were
   built and tested separately).
2. **Build-and-verify loops, not one-shot generation.** Each layer (loaders
   → chunking → index → retrieval → MCP tools → orchestrator → Flask app)
   was written, then immediately executed against the real policy corpus
   and real mock data in the sandbox, with failures fed back into the next
   edit. This caught several real bugs (see below) that would not have
   been visible from reading the code alone.
3. **Tests written against the same running code**, not against an
   imagined API — e.g., `tests/test_mcp_tools.py`'s HTTP-transport tests
   spin up the actual Flask MCP server on a background thread and hit it
   over real HTTP, rather than mocking the transport.

## What worked well

- **Iterative debugging against real output caught citation-quality bugs
  early.** The first pass of `app/rag/loaders.py` mis-extracted document
  titles and, more seriously, mis-extracted the canonical `SOL-XXX-###`
  Document ID for the HTML and PDF sources — one HTML document was even
  assigned another document's ID due to a footer cross-reference being
  matched before the document's own header. Because the ingestion script
  was actually run and its per-document ID/title table was printed and
  inspected after every change, this was caught and fixed (three
  incremental patches to `_infer_title`/`_infer_doc_id`) before it ever
  reached the agent or evaluation layer, where it would have silently
  produced wrong citations.
- **Running the evaluation suite immediately surfaced a routing gap.** The
  first version of `classify_intent()` failed the
  `pto_request_guidance` workflow test for the phrasing "I want to take 2
  weeks of PTO in October" (it matched the generic `policy_qa` path
  instead), because the keyword list required tighter substrings like
  "take pto" that don't appear when a quantity is inserted mid-phrase
  ("take **2 weeks of** pto"). This was only visible by executing the test
  and reading the failure, not from a static read-through — a one-line
  broadened rule fixed it.
- **End-to-end offline mode was validated, not assumed.** Rather than just
  writing an LLM client and an "offline fallback" and hoping the fallback
  path worked, the entire agent (all 7 workflows, all 8 tools, both
  transports) was actually exercised with no `LLM_API_KEY` set, in the
  same sandbox that has no network access at all — which is a stronger
  guarantee than a mocked test would have given, since it's the same
  offline constraint a grader without an API budget would face.
- **Two MCP transports sharing one schema source of truth** eliminated an
  entire class of "the HTTP server's tool list doesn't match what the
  agent expects" bugs, because both are exercised by the same test file
  (`test_mcp_tools.py`) against the same `mcp_server.server.build_registry()`.

## What didn't work well / needed correction

- **The `mcp` official SDK could not be verified in the sandbox** (no
  network access to `pip install mcp`), so `mcp_server/official_sdk_server.py`
  is written carefully from documented API patterns but **has not been
  executed**, unlike every other file in this repository. This is flagged
  explicitly in that file's docstring and in `design-and-evaluation.md`
  Section 5.1, and it's the reason the default, tested MCP transport is
  the hand-rolled JSON-RPC-over-HTTP server (`mcp_server/http_server.py`)
  rather than the official SDK. Before relying on
  `official_sdk_server.py` in a real deployment, run it locally with
  `pip install mcp` and re-verify against the current SDK version.
- **TF-IDF's lexical-overlap reranking produces occasional false-positive
  relevance on off-topic queries** (documented in
  `evaluation/results.md` "Known limitations" — e.g., "New York" partially
  matching "New Hire"). This was caught by a failing unit test
  (`test_irrelevant_query_yields_low_confidence`) during development; the
  fix was to raise the guardrail's minimum-score threshold and rely on the
  keyword-based scope check as the primary out-of-scope defense rather than
  retrieval score alone, and to document the residual risk rather than
  claim it's fully solved.
- **PDF text extraction ordering is not always document order.** Canvas-
  drawn footer text (page numbers, "Internal Use Only") in the generated
  policy PDFs sometimes extracts *before* the body text that visually
  precedes it on the page, which broke a naive "first non-header line is
  the title" heuristic. This needed three rounds of tightening the title-
  detection heuristic (skip footer-shaped lines, require a minimum length,
  require at least one letter) before it reliably worked across all four
  PDF policy documents — a good example of a "simple" text-extraction task
  having more real-world edge cases than it first appears.
- **No LLM was available to actually test the LLM-backed synthesis path**
  in this environment (no network access for API calls). `app/agent/llm.py`
  is written against the standard OpenAI Chat Completions request/response
  shape and should work as-is against any compatible endpoint, but — in the
  same spirit as the point above about the official MCP SDK — this is
  flagged as the one major code path that was reviewed carefully but not
  executed, and anyone deploying with `LLM_API_KEY` set should do a manual
  smoke test of a few `/chat` calls before trusting it in front of users.

## Takeaway

The most valuable pattern in this build was **treating "the AI wrote code
that looks right" and "the code actually ran correctly against real data"
as two different, both-necessary milestones**, and only writing the design
rationale and evaluation numbers in the documentation *after* the second
milestone was reached for each component. The two exceptions noted above
(official MCP SDK, live LLM calls) are the parts of the system that only
reached the first milestone, and they're called out as such rather than
presented with the same confidence as everything that was actually run.
