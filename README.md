# Solarium HR Assistant — Agentic RAG + MCP System

An agentic AI system that answers Solarium (fictional company) HR policy and
operations questions, grounded in a real policy corpus via Retrieval-
Augmented Generation, with an agent orchestrator that plans, selects tools,
and calls Model Context Protocol (MCP) tools over mock structured HR data
(employee profiles, PTO/benefits balances, support tickets).

**Live demo:** see [`Deployed.md`](Deployed.md) for the deployed URL, health
endpoint, and cold-start notes.

## What this is

```
Employee question ──▶ Flask chat UI ──▶ Agent Orchestrator ──▶ MCP tools
                                              │                    │
                                    (rule-based intent          8 tools:
                                     routing + LLM or            3 policy/RAG
                                     offline synthesis)           5 mock HR data
                                              │                    │
                                              ▼                    ▼
                                     Grounded, cited answer   TF-IDF vector index
                                     + operational trace       over policy_corpus/
```

See [`design-and-evaluation.md`](design-and-evaluation.md) for the full
architecture diagram and every design decision's rationale.

- **RAG**: parses Markdown, HTML, PDF, and TXT policy documents
  (`policy_corpus/`), heading-aware chunks them, embeds with a free local
  TF-IDF vectorizer (`scikit-learn`, zero cost/zero network), and retrieves
  with cosine similarity + a lexical reranking pass.
- **Agent**: a deterministic, rule-based orchestrator (`app/agent/`) that
  classifies intent, decides which MCP tool(s) to call, runs 2+ multi-step
  workflows (remote work eligibility, PTO request guidance, benefits
  questions, expense compliance, onboarding checklists), and gates every
  irreversible action (ticket creation, email drafting) behind explicit user
  confirmation.
- **MCP**: 8 tools exposed via a dependency-free JSON-RPC 2.0-over-HTTP
  server (`mcp_server/`) implementing the MCP `tools/list` / `tools/call`
  contract, plus an in-process transport for tests/dev and an optional
  official-SDK variant (`mcp_server/official_sdk_server.py`).
- **Web app**: Flask, with a responsive, from-scratch chat UI (`app/static`,
  `app/templates`) — no JS framework/build step required.
- **Mock data**: synthetic employee/PTO/benefits/ticket CSV+JSON records
  (`mock_data/`) — see `mock_data/README_DATA.md`.

## Project structure

```
app/                    Flask web app, RAG pipeline, agent orchestrator
  main.py                 Flask app factory, routes: /, /chat, /health, /api/*
  config.py                env-var configuration (no secrets hard-coded)
  mcp_client.py            unified MCP client (inprocess | http transport)
  rag/                     loaders, chunking, TF-IDF index, retrieval, ingest CLI
  agent/                   orchestrator, LLM client, prompts, guardrails
  static/, templates/      chat UI (HTML/CSS/JS)
mcp_server/              MCP tool server
  tool_registry.py          MCP-style tool registration + tools/list + tools/call
  server.py                 registers all 8 tools with JSON-Schema args
  http_server.py            JSON-RPC 2.0 HTTP transport (Flask blueprint)
  official_sdk_server.py    optional: same tools via the official `mcp` SDK
  mock_data_store.py        loads mock_data/ CSV+JSON into memory
  tools/                    policy_tools.py, hr_data_tools.py
policy_corpus/            the 11-document Solarium policy corpus (md/html/pdf/txt)
mock_data/                synthetic employees/PTO/benefits/tickets
evaluation/               eval_questions.json, run_eval.py, results.md/.json
tests/                    unit tests (health, RAG, MCP tools, agent workflows)
scripts/build_index.py    CLI wrapper for RAG index build
.github/workflows/ci.yml  CI/CD pipeline
design-and-evaluation.md  architecture, design rationale, full eval results
ai-tooling.md              which AI coding tools were used and how
Deployed.md                 deployed URL + cold-start notes
```

## Setup

### 1. Virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment variables

```bash
cp .env.example .env
# Edit .env if you want LLM-based answer synthesis (optional -- see below).
```

`LLM_API_KEY` is **optional**. If unset, the agent still fully retrieves,
calls MCP tools, and synthesizes grounded, cited answers using a
deterministic offline template instead of an LLM rewrite — the whole system
is usable and testable with **zero API cost**. Set `LLM_API_KEY` (and
optionally `LLM_BASE_URL`/`LLM_MODEL`) to point at any OpenAI Chat
Completions-compatible endpoint (OpenAI, Groq, OpenRouter, a local Ollama
server, etc.) to enable natural-language LLM synthesis instead.

**Secrets are never committed.** `.env` is git-ignored; all configuration is
read from environment variables at runtime (`app/config.py`).

## Local run

### Build the RAG index (required once, and after any policy_corpus/ change)

```bash
python -m app.rag.ingest
# or: python scripts/build_index.py
```

This is deterministic (fixed chunking parameters, no sampling) — the same
corpus always produces a byte-identical index.

### Run the web app (single-service mode — MCP tools run in-process)

```bash
python -m app.main
# or: flask --app app.main run --debug
```

Visit **http://localhost:8000**. Try the sidebar's demo-task buttons, or
ask something like *"How many weeks of parental leave do I get?"*.

### Run the MCP server as a separate process (optional, HTTP transport)

```bash
python -m mcp_server.run_http                 # starts on :8001
# in another terminal:
MCP_TRANSPORT=http MCP_SERVER_URL=http://localhost:8001 python -m app.main
```

This proves out the "MCP server as a separate service, called over HTTP"
deployment mode locally before deploying it as two separate free-tier
services.

## Testing

```bash
python -m pytest tests/ -v
```

Covers: app startup (`test_health.py`), RAG loading/chunking/retrieval
across all 4 formats (`test_rag.py`), MCP tool discovery + calls over both
the in-process and HTTP transports (`test_mcp_tools.py`), and agent
workflows/guardrails/confirm-then-act safety (`test_agent.py`). 30 tests,
all passing with zero external dependencies (no LLM key, no network).

## Evaluation

```bash
python -m evaluation.run_eval
```

Runs the 26-question evaluation set (`evaluation/eval_questions.json`) and
reports groundedness, citation accuracy, tool-selection accuracy, escalation
accuracy, action-safety pass rate, latency p50/p95, and a retrieval-`k`
ablation. Full results and narrative: [`evaluation/results.md`](evaluation/results.md).

## Reproducing the 2 required agentic demo tasks

Via the UI: click either demo-task button in the left sidebar (also
includes a 3rd action-confirmation demo).

Via API:
```bash
# Demo 1 — remote work eligibility (multi-step: RAG + employee profile)
curl -s localhost:8000/chat -H 'Content-Type: application/json' -d '{
  "message": "Can I work remotely from Portugal for a month?",
  "employee_id": "EMP-0006"
}' | python3 -m json.tool

# Demo 2 — PTO request guidance (multi-step: PTO balance + RAG)
curl -s localhost:8000/chat -H 'Content-Type: application/json' -d '{
  "message": "I want to take 2 weeks of PTO in October, what do I need to know?",
  "employee_id": "EMP-0010"
}' | python3 -m json.tool
```
The exact task list (with expected tools) is also served at
`GET /api/demo-tasks` for programmatic reproduction.

## Deployment (Render / Railway / equivalent free tier)

Full click-through steps are in [`design-and-evaluation.md` "Deployment
Architecture"](design-and-evaluation.md#deployment-architecture); summary:

**Single-service mode (simplest, recommended for free tier):**
1. Push this repo to GitHub.
2. On Render: New → Web Service → connect the repo (or use the included
   `render.yaml` Blueprint: New → Blueprint → select this repo).
3. Build command: `pip install -r requirements.txt`
   Start command: `python -m app.rag.ingest && gunicorn app.main:app --bind 0.0.0.0:$PORT`
4. Set env vars from `.env.example` (at minimum `FLASK_SECRET_KEY`; leave
   `LLM_API_KEY` unset for zero-cost offline mode, or set it for LLM
   synthesis).
5. Deploy. MCP tools run in-process automatically (`MCP_TRANSPORT=inprocess`).

**Two-service mode (MCP server deployed separately, called over HTTP):**
1. Deploy a second Render/Railway web service for the MCP server:
   Start command: `python -m app.rag.ingest && python -m mcp_server.run_http`
2. On the main web service, set `MCP_TRANSPORT=http` and
   `MCP_SERVER_URL=https://<your-mcp-service>.onrender.com`.
3. Redeploy the main service.

Railway: identical build/start commands via `railway.json`, or paste them
into the Railway dashboard's service settings.

**No paid database required** — storage is committed CSV/JSON files
(`mock_data/`) plus a small local vector index rebuilt on every deploy
(`data/rag_index.pkl`, git-ignored, regenerated by `python -m app.rag.ingest`
in the start command).

**Cold starts:** free-tier services spin down after inactivity and take
~30-60s to wake on the next request. See [`Deployed.md`](Deployed.md) for
current measured cold-start behavior on the live deployment.

## CI/CD

`.github/workflows/ci.yml` runs on every push/PR to `main`: installs
dependencies, builds the RAG index, runs an import/start smoke check, runs
the full `pytest` suite (including MCP tool discovery/call tests), uploads
the evaluation report as a build artifact, and only triggers a deploy hook
if the test job succeeded (`needs: test`). To wire up real auto-deploy, add
a `RENDER_DEPLOY_HOOK_URL` repository secret pointing at your Render
service's deploy hook — see the workflow file for details, or simply enable
Render/Railway's own "auto-deploy on push" (also gated on your CI passing if
you enable required status checks on the `main` branch in GitHub).

## Security notes

- No secrets are hard-coded anywhere; all sensitive config is read from
  environment variables (`app/config.py`) and `.env` is git-ignored.
- User input is length-capped (`MAX_MESSAGE_LENGTH`) before reaching the
  agent/LLM layer, and a basic per-IP in-memory rate limiter protects
  `/chat` (`RATE_LIMIT_PER_MINUTE`).
- All chat text is rendered client-side through an escape-first, allow-list
  markdown-lite renderer (`static/js/chat.js`) — never raw `innerHTML` of
  unescaped text — to prevent stored/reflected XSS.
- Every response sets `X-Content-Type-Options`, `X-Frame-Options`, and
  `Referrer-Policy` headers.
- Irreversible actions (`create_mock_hr_ticket`, `draft_hr_email`) are never
  executed on the first agent turn — they always return a `pending_action`
  requiring an explicit follow-up confirmation (see
  `app/agent/orchestrator.py` and `tests/test_agent.py`).
- All employee/PTO/benefits/ticket data is synthetic (see
  `mock_data/README_DATA.md`) — no real PII is used anywhere in this repo.

## License / usage

This is a course project artifact built around a fictional company
("Solarium") and entirely synthetic data. No real company, employee, or
policy data is used anywhere in this repository.
