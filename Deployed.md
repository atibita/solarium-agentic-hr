# Deployed.md

## Deployment status

This repository is **deployment-ready but not yet deployed to a live URL**
as part of this exercise — no Render/Railway account/hosting action was
taken in the environment this project was built in. Everything needed to
deploy it in a few minutes is included:

- `render.yaml` — Render Blueprint (both single-service and two-service
  modes described in `README.md` "Deployment")
- `railway.json` — Railway build/start configuration
- `Procfile` — generic buildpack-style start command
- Full click-through steps in `README.md` → "Deployment" and
  `design-and-evaluation.md` → "Deployment Architecture"

**When you deploy this yourself, fill in the section below** with your
actual URLs and observed cold-start timing — the template and the exact
commands to gather that data are provided so this stays a 2-minute task.

---

## Fill in after deploying

**Web app URL:** `https://<your-service-name>.onrender.com`
*(or the equivalent Railway-generated domain)*

**Health check URL:** `https://<your-service-name>.onrender.com/health`

Expected response shape:
```json
{
  "status": "ok",
  "app": "solarium-hr-assistant",
  "mcp": {"connected": true, "transport": "inprocess", "tool_count": 8},
  "llm_configured": false
}
```

**MCP server URL** (only if deployed as a separate service):
`https://<your-mcp-service-name>.onrender.com/mcp/health`

**Deployment mode used:** ☐ single-service (default) ☐ two-service (MCP separate)

**LLM configured:** ☐ yes (`LLM_API_KEY` set — model: __________) ☐ no (offline template mode)

## Measuring cold-start behavior

Render/Railway free-tier services spin down after a period of inactivity.
To measure your actual cold-start time after deploying:

```bash
# Wait until the service has been idle (Render free tier: ~15 minutes),
# then time the first request:
time curl -s https://<your-service-name>.onrender.com/health

# Then immediately measure a warm request:
time curl -s https://<your-service-name>.onrender.com/health
```

Record the results here:

| Run | Latency | Notes |
|---|---|---|
| Cold start (first request after idle) | `_____ s` | |
| Warm (immediately after) | `_____ ms` | |
| Warm `/chat` call, offline synthesis | `_____ ms` | should match `evaluation/results.md`'s in-process numbers (~2-30ms server-side) plus network RTT |
| Warm `/chat` call, LLM synthesis (if configured) | `_____ ms` | dominated by the LLM API call, typically 1-3s |

**Expected cold-start range:** approximately **30-60 seconds** for a Render
free-tier "web" service (build already complete; the wake-up cost is
process boot + `python -m app.rag.ingest`, which — per the timing already
logged by that command in `evaluation/results.md` — takes well under one
second, so essentially all of the 30-60s is the platform's own wake latency,
not this application's startup work).

If running in two-service mode, the **first** `/chat` call after both
services have been idle will pay **two** cold starts (web app, then its
first outbound call to the MCP service) — expect roughly double the
single-service cold-start figure on that first request only.

## Notes for graders / testers

- If you hit the deployed URL and get no response within ~60 seconds on
  the very first try, that's the expected free-tier cold start — retry
  once.
- The two required agentic demo tasks (see `README.md` → "Reproducing the
  2 required agentic demo tasks") work identically against the deployed URL
  and locally — just replace `localhost:8000` with the deployed URL in the
  `curl` examples, or use the sidebar buttons in the deployed chat UI.
- `GET /health` is safe to poll for a quick liveness/MCP-connectivity check
  without exercising the full RAG/agent pipeline.
