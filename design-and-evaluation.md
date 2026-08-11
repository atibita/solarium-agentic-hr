# Design & Evaluation — Solarium HR Assistant

## 1. Architecture

### 1.1 Text architecture diagram

```
                              ┌─────────────────────────────┐
                              │        Browser (chat UI)     │
                              │  app/templates/index.html    │
                              │  app/static/{css,js}         │
                              └───────────────┬───────────────┘
                                              │ POST /chat, GET /health, GET /api/*
                                              ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                       Flask Web App  (app/main.py)                        │
│  routes: /  /chat  /health  /api/demo-tasks  /api/sample-employees        │
│  security: rate limiting, input length caps, security headers            │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │ orchestrator.handle(message, employee_id, …)
                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                 Agent Orchestrator (app/agent/orchestrator.py)            │
│  1. classify_intent()            — deterministic keyword routing         │
│  2. guardrails                    — in-scope check, evidence-sufficiency  │
│  3. workflow handler               — 1..N tool calls via MCP client        │
│  4. synthesize()                  — LLM (if configured) or offline template│
│  5. trace                          — concise operational log (no hidden CoT)│
└───────────────────┬───────────────────────────────────┬───────────────────┘
                    │ MCPClient.call_tool(name, args)    │ LLMClient.complete()
                    ▼                                     ▼
┌─────────────────────────────────────┐        ┌───────────────────────────┐
│   app/mcp_client.py (MCP client)     │        │  app/agent/llm.py          │
│   transport = inprocess | http        │        │  OpenAI-compatible HTTP,   │
└───────────────┬───────────────────────┘        │  or offline template       │
                │                                 │  fallback (no key needed) │
    inprocess   │   http (JSON-RPC 2.0)           └───────────────────────────┘
   (same OS     │   POST /mcp/rpc
    process)    │
                ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                    MCP Tool Server (mcp_server/)                          │
│  tool_registry.py   — MCP-style tools/list + tools/call, schema validation │
│  server.py           — registers 8 tools with JSON-Schema arguments        │
│  http_server.py       — Flask blueprint exposing the JSON-RPC 2.0 surface   │
│                                                                             │
│  Policy/RAG tools (tools/policy_tools.py):                                │
│    search_policy_documents, get_policy_section, check_policy_compliance   │
│  Mock structured-data tools (tools/hr_data_tools.py):                      │
│    lookup_employee_profile, check_pto_balance, lookup_benefits_status,    │
│    create_mock_hr_ticket*, draft_hr_email*      (*side-effecting, gated)  │
└───────────┬─────────────────────────────────────────────┬─────────────────┘
            │                                              │
            ▼                                              ▼
┌───────────────────────────────┐          ┌───────────────────────────────┐
│   RAG Index (app/rag/)         │          │  Mock Data Store               │
│   loaders → chunking → TF-IDF  │          │  (mcp_server/mock_data_store)  │
│   VectorIndex (sklearn)         │          │  mock_data/*.csv, *.json       │
│   built from policy_corpus/     │          │  employees, PTO, benefits,     │
│   (md, html, pdf, txt)          │          │  offices, tickets              │
└───────────────────────────────┘          └───────────────────────────────┘
```

### 1.2 Component summary

| Component | Location | Role |
|---|---|---|
| Web app | `app/main.py` | Flask routes, security headers, rate limiting |
| Agent orchestrator | `app/agent/orchestrator.py` | Intent routing, workflow execution, tracing |
| Guardrails | `app/agent/guardrails.py` | Scope check, evidence-sufficiency, confirmation gate |
| LLM client | `app/agent/llm.py` | Optional LLM synthesis, offline fallback |
| MCP client | `app/mcp_client.py` | Unified tool-call interface (inprocess/http) |
| MCP tool server | `mcp_server/` | Tool registry, schemas, HTTP transport |
| RAG pipeline | `app/rag/` | Loaders, chunking, TF-IDF index, retrieval |
| Mock data store | `mcp_server/mock_data_store.py` | In-memory CSV/JSON-backed HR data |

## 2. RAG Design

### 2.1 Parsing (`app/rag/loaders.py`)
Four format-specific loaders (Markdown, HTML via BeautifulSoup, PDF via
`pypdf`, plain text) normalize every source into a common `RawDocument`
(doc_id, title, source_format, text). Each loader:
- Infers the canonical `SOL-<AREA>-<NUMBER>` Document ID from the header
  block every policy document shares (not just the filename), so citations
  always match the ID the policy corpus itself defines.
- Preserves heading structure as markdown-style `## `/`### ` markers so a
  single downstream chunker works identically across all four formats
  (HTML `<h2>`/`<h3>`/tables/lists are rebuilt into that shape; PDF text is
  scanned for numbered-heading patterns and promoted back to `## `).
- Strips PDF-extraction artifacts (stray control characters from bullet
  glyphs) so citation snippets are always clean, human-readable text.

### 2.2 Chunking (`app/rag/chunking.py`)
**Strategy: heading-aware chunking with a token-window fallback.**
Policy documents are already organized into numbered sections. Splitting on
`## `/`### ` headings keeps each chunk topically coherent — a PTO carryover
rule is never split mid-sentence from its neighbor about accrual rates —
which is what actually drives citation precision for a policy Q&A system.
Sections still too long (dense tables) are further split with a 220-word
window and 40-word overlap so no chunk exceeds a size that would dilute a
TF-IDF vector's discriminating power. Both parameters are fixed (no random
sampling), so `python -m app.rag.ingest` is fully deterministic and
reproducible — a requirement explicitly called out in the project spec.

Result on the current 11-document corpus: **104 chunks**.

### 2.3 Embedding / vector store (`app/rag/index.py`)
**Choice: local TF-IDF (scikit-learn) + cosine similarity, not a neural
embedding API.**
- **Zero cost, zero network dependency** — works identically in CI, in a
  free-tier host with no outbound calls, and fully offline. This matters
  because the whole system (RAG, agent, MCP tools) needs to be runnable and
  gradeable with no API budget.
- **Deterministic and fast to rebuild** on every deploy — no model download,
  no cold-start embedding latency.
- For a single-company policy corpus of this size (~40 pages, 104 chunks),
  TF-IDF + cosine similarity reliably retrieves the correct section for the
  overwhelming majority of keyword-bearing HR questions, which the
  evaluation set (Section 5) confirms: **100% citation accuracy** across 15
  policy questions plus the required multi-document question.
- The `VectorIndex` class is intentionally the *only* place that would need
  to change to swap in FAISS/Chroma + a sentence-transformers or OpenAI
  embedding model — nothing in the RAG retrieval interface, the MCP tools,
  or the agent orchestrator depends on TF-IDF specifically. This is
  documented as the natural "next step" for a larger, more linguistically
  varied corpus where lexical overlap alone would retrieve less reliably
  (e.g., synonyms like "time off" vs. "PTO" without any shared n-grams).

### 2.4 Retrieval (`app/rag/retrieve.py`)
Top-k retrieval over a larger candidate pool (`3k`), then a lightweight
**lexical reranking** pass (`0.7 * cosine_similarity + 0.3 * keyword_overlap`)
that boosts chunks containing an exact policy term the query used (e.g.,
"bereavement") over looser TF-IDF neighbors. `doc_id_filter` supports
scoping a search to a single already-relevant document (used by workflow
handlers — e.g., the remote-work workflow searches `SOL-OPS-201` first).
Default `k=5` (see Section 6.2's ablation for why).

### 2.5 Citation metadata
Every chunk persists `doc_id`, `doc_title`, `section`, `source_format`, and
the original `text` (from which a clean snippet is derived) — enough for
every RAG-backed tool response and every final answer to cite a specific
Document ID and section, and for a UI citation chip to show a supporting
snippet without a second lookup.

## 3. Agent Orchestration Design

### 3.1 Framework choice: deterministic rule-based orchestration
The orchestrator (`app/agent/orchestrator.py`) uses **explicit, readable
`if`/`elif` intent classification and hand-written workflow handlers**,
not a general-purpose agent framework (LangChain agents, AutoGPT-style
free-form tool loops, etc.). Rationale:
- **Determinism and reproducibility.** With a fixed set of 8 known tools,
  rule-based routing means the same question always selects the same
  tool(s) in the same order — critical for the evaluation set's tool-
  selection-accuracy metric to mean anything across repeated runs.
- **Auditability.** Every routing decision is a readable branch in source
  code, not an opaque LLM planning call that might change behavior between
  model versions or temperature settings.
- **Works with zero LLM budget.** The full agent — intent routing, tool
  selection, multi-step workflows, guardrails — runs correctly with no LLM
  configured at all (see `LLMDisabledError` fallback in `orchestrator.py`),
  which the evaluation suite (Section 5) exercises directly. The LLM (when
  configured) is used only where it adds the most value: turning retrieved
  evidence into fluent natural language, not deciding *which* evidence to
  retrieve.
- **Trade-off, honestly stated:** rule-based routing is less flexible than
  an LLM planner for paraphrases far outside the keyword patterns in
  `classify_intent()`. When that happens, the system degrades gracefully to
  the generic `policy_qa` handler (still grounded and cited) rather than
  failing outright — see the "Known limitations" note in
  `evaluation/results.md`.

### 3.2 Multi-step workflows (≥2 required; 5 implemented)
1. **`remote_work_eligibility`** — retrieve `SOL-OPS-201` evidence scoped to
   eligibility/location rules → look up the employee's current work model
   via `lookup_employee_profile` (if an employee ID is known) → synthesize
   eligibility guidance combining both.
2. **`pto_request_guidance`** — `check_pto_balance` for the employee →
   retrieve `SOL-HR-101` request/approval-process evidence → synthesize
   guidance combining the employee's actual balance with the policy's
   notice/approval rules.
3. **`benefits_question`** — `lookup_benefits_status` → retrieve `SOL-HR-103`
   evidence → synthesize.
4. **`expense_compliance`** — `check_policy_compliance` (amount-vs-cap
   check) → retrieve `SOL-FIN-301` evidence → synthesize.
5. **`onboarding_checklist`** — retrieve `SOL-HR-104` evidence (30/60/90-day
   plan, Day 1 checklist) → optionally `lookup_employee_profile` → synthesize
   a checklist.

Two additional **action workflows** (`hr_ticket_action`, `draft_email_action`)
implement the confirm-then-act pattern described in Section 4.

### 3.3 Trace format
Every response includes a `trace: TraceStep[]` — `step`, `detail`,
`tool_name`, `tool_arguments`, `tool_ok`, `latency_ms` — covering intent
classification, every tool call (with arguments and a human-readable result
summary), guardrail decisions, and answer synthesis. This is a **concise
operational trace, not chain-of-thought**: no hidden model reasoning is
exposed, only "what the system actually did," matching the project's "do
not expose hidden chain-of-thought; provide concise operational traces
instead" requirement.

## 4. Safety Guardrails

| Guardrail | Location | Behavior |
|---|---|---|
| Out-of-corpus refusal | `guardrails.is_in_scope` | Keyword-scope check before any retrieval; declines and redirects (never attempts to answer from outside knowledge) |
| Insufficient-evidence refusal | `guardrails.has_sufficient_evidence` | If top retrieval score < `MIN_RETRIEVAL_SCORE` (0.20), says so explicitly rather than guessing |
| Fact vs. recommendation separation | `prompts.SYSTEM_PROMPT` rule 3 | LLM instructed to prefix interpretation/advice with "My suggestion:"; offline template only ever states retrieved facts |
| Missing-employee-ID clarification | workflow handlers | Tool-requiring workflows ask for an employee ID rather than guessing or omitting the data |
| Ambiguous/empty request clarification | `orchestrator.handle` | Empty or clearly incomplete requests return `clarification_needed=true` |
| **Irreversible-action prevention** | `orchestrator._handle_ticket_action`, `_handle_draft_email_action`, `_execute_confirmed_action` | `create_mock_hr_ticket`/`draft_hr_email` are **never called on the first turn** — the orchestrator always returns a `pending_action` describing exactly what would happen, and only calls the tool after an explicit follow-up `confirm: true` round-trip. Verified by `tests/test_agent.py::test_ticket_action_requires_confirmation_before_executing`. |
| Unavailable-MCP-tool handling | `orchestrator._call_tool` / `MCPToolUnavailableError` | HTTP transport failures are caught and logged as a trace step with `tool_ok=false`; the workflow degrades (e.g., answers from policy alone if a data tool is unreachable) rather than crashing |
| Input hardening | `app/main.py` | Message length capped, per-IP rate limiting, XSS-safe client-side rendering, standard security headers |

## 5. MCP Architecture

### 5.1 Transport choice
**Two transports, one schema source of truth (`mcp_server/server.py`):**
1. **In-process** (default, `MCP_TRANSPORT=inprocess`) — the agent imports
   `mcp_server.server.get_registry()` directly and calls
   `registry.call_tool()`. Used for local dev, unit tests, and the
   free-tier "single service" deployment mode explicitly allowed by the
   project spec. Calls still go through the *same* `ToolRegistry` schema-
   validation layer the HTTP transport uses — this is not a bypass of the
   MCP tool layer, it is the identical call path running in the same OS
   process instead of over a socket.
2. **HTTP** (`MCP_TRANSPORT=http`) — a dependency-free JSON-RPC 2.0 server
   (`mcp_server/http_server.py`) implementing MCP's `tools/list` and
   `tools/call` message shapes over `POST /mcp/rpc`, for the "MCP server
   deployed as a separate service" mode. Verified end-to-end against a real
   running HTTP server in `tests/test_mcp_tools.py::HttpTransportTests`.

An optional **official-SDK variant** (`mcp_server/official_sdk_server.py`,
using `mcp.server.fastmcp.FastMCP`) shows how the same tool functions map
onto the official `mcp` PyPI package's `streamable-http`/`stdio` transports,
for anyone who needs strict protocol-library compliance rather than this
project's hand-rolled (but message-shape-compatible) JSON-RPC surface. It
is not installed by default (`mcp` is not in `requirements.txt`) precisely
because the custom registry is easier to unit-test deterministically with
zero extra dependencies in a free-tier CI environment — see the module's
docstring for the full trade-off.

### 5.2 Tool schemas (all 8 tools; JSON-Schema `inputSchema` as registered)

| Tool | Required args | Uses | Side effects |
|---|---|---|---|
| `search_policy_documents` | `query` | RAG index | none |
| `get_policy_section` | `document_id`, `section` | RAG index | none |
| `check_policy_compliance` | `topic` | RAG index + rule check | none |
| `lookup_employee_profile` | `employee_id` | mock data | none |
| `check_pto_balance` | `employee_id` | mock data | none |
| `lookup_benefits_status` | `employee_id` | mock data | none |
| `create_mock_hr_ticket` | `employee_id`, `category`, `subject` | mock data | **simulated write** (in-memory only); confirm-gated |
| `draft_hr_email` | `employee_id`, `purpose` | mock data | **produces draft text only, never sends**; confirm-gated |

Full JSON-Schema definitions live in `mcp_server/server.py::build_registry()`.

### 5.3 Discovery and invocation
The agent's `MCPClient` (`app/mcp_client.py`) exposes exactly two methods —
`list_tools()` and `call_tool(name, arguments)` — regardless of transport.
`ToolRegistry.call_tool()` validates arguments against the tool's JSON
Schema (`required` fields, unknown-field rejection) before invoking the
Python handler, and always returns a structured `{ok, result, error,
latency_ms}` shape so the orchestrator can log a trace step and degrade
gracefully on failure.

## 6. Deployment Architecture

### 6.1 Single-service mode (default, simplest)
Web app + agent orchestrator + RAG index + MCP tool registry + mock data
all run in **one** Render/Railway free-tier web service process. The MCP
HTTP blueprint (`mcp_server.http_server.mcp_bp`) is still mounted at
`/mcp/*` inside this same Flask app (`MOUNT_MCP_IN_APP=true`) purely so the
HTTP surface can be smoke-tested even in single-service mode — the agent
itself uses the faster in-process path by default.

### 6.2 Two-service mode (MCP server deployed separately)
The MCP server runs as its own free-tier service
(`python -m mcp_server.run_http`), and the web app is configured with
`MCP_TRANSPORT=http` + `MCP_SERVER_URL=https://<mcp-service-url>`. Both
services rebuild their RAG index on start (`python -m app.rag.ingest`) so
there's no shared filesystem dependency between them. No paid database is
required in either mode — storage is committed CSV/JSON files plus a
locally rebuilt vector index (`data/rag_index.pkl`, git-ignored).

### 6.3 Cold starts
Free-tier Render/Railway services spin down after inactivity; the next
request triggers a ~30-60s cold start (build already done, just process
boot + RAG index rebuild, which takes well under 1 second per the timing
logged by `app.rag.ingest`). See `Deployed.md` for current measured numbers
against the live deployment.

## 7. Evaluation

Full methodology, the 26-question evaluation set, all metrics, and the
retrieval-`k` ablation are in [`evaluation/results.md`](evaluation/results.md)
(narrative) and `evaluation/results.json` (machine-readable, regenerated by
`python -m evaluation.run_eval`). Headline results from the most recent run:

| Metric | Result |
|---|---|
| Groundedness rate | 100% |
| Citation accuracy | 100% |
| Multi-document coverage (required complex question) | Pass — 3 documents cited |
| Tool selection accuracy | 100% |
| Escalation/clarification accuracy | 100% |
| Out-of-scope refusal rate | 100% |
| Action-safety pass rate | 100% |
| Latency p50 / p95 (in-process, offline synthesis) | 1.77ms / 2.91ms |

See `evaluation/results.md` for the retrieval-`k` ablation (k=3/5/8/12) and
an honest discussion of latency caveats (LLM call time and free-tier cold
starts are **not** included in the in-process numbers above — see that
document's "Cold start vs. warm latency" section).

## 8. Two Required Agentic Demo Tasks — Expected Tool-Call Sequence

**Demo 1 — Remote work eligibility** (`GET /api/demo-tasks` id `demo-1-remote-work`)
> "Can I work remotely from Portugal for a month?" (employee EMP-0006)

1. `classify_intent` → `remote_work_eligibility`
2. `search_policy_documents(query="... eligibility remote hybrid", doc_id="SOL-OPS-201")`
3. `lookup_employee_profile(employee_id="EMP-0006")`
4. `synthesize_answer` — combines SOL-OPS-201 Section 5 (Temporary Work
   Location, 10-business-day notice for 30+ day/international trips) with
   the employee's current work model/office.

**Demo 2 — PTO request guidance** (`demo-2-pto-request`)
> "I want to take 2 weeks of PTO in October, what do I need to know?" (EMP-0010)

1. `classify_intent` → `pto_request_guidance`
2. `check_pto_balance(employee_id="EMP-0010")`
3. `search_policy_documents(query="PTO request notice approval process ...", doc_id="SOL-HR-101")`
4. `synthesize_answer` — combines the employee's actual PTO balance with
   SOL-HR-101 Section 3's 2-week advance notice rule.

**Demo 3 (bonus) — Mock ticket creation with confirm-then-act** (`demo-3-ticket-action`)
> "My laptop screen cracked, can you open an IT ticket?" (EMP-0010)

1. `classify_intent` → `hr_ticket_action`
2. Orchestrator prepares `create_mock_hr_ticket` arguments but does **not**
   call the tool — returns `pending_action` + asks for confirmation.
3. User replies "confirm" → orchestrator calls
   `create_mock_hr_ticket(employee_id="EMP-0010", category="IT", ...)`.
4. `synthesize` — confirms the mock ticket ID created.
