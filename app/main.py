"""
app/main.py
-------------
The Solarium HR Assistant web application (Flask).

Routes:
  GET  /                render the chat UI
  POST /chat             agentic chat endpoint -> {answer, citations, trace, ...}
  GET  /health            liveness + MCP connectivity status
  GET  /api/demo-tasks    the >=2 reproducible agentic demo tasks (for graders)
  GET  /api/sample-employees  a few employee IDs to try in the UI dropdown

Security notes (see design-and-evaluation.md "Security" section for detail):
  - No secrets are hard-coded; all config comes from environment variables
    (app/config.py).
  - Every response is auto-escaped by Jinja2 templating (chat text is
    rendered client-side via textContent, not innerHTML, for the same
    reason -- see static/js/chat.js).
  - Basic per-IP in-memory rate limiting protects the free-tier deployment
    from accidental abuse (not a substitute for a real WAF, documented as a
    known limitation).
  - Input length is capped (MAX_MESSAGE_LENGTH) before it ever reaches the
    agent/LLM layer.
  - No irreversible action is ever executed without an explicit, separate
    confirmation round-trip (see agent/orchestrator.py).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from flask import Flask, jsonify, render_template, request

from .agent.orchestrator import AgentOrchestrator
from .config import Config
from .mcp_client import MCPClient

# mcp_server is only imported (and its Flask blueprint mounted) when running
# in single-service mode -- see create_app().


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    mcp_client = MCPClient(transport=Config.MCP_TRANSPORT, server_url=Config.MCP_SERVER_URL)
    orchestrator = AgentOrchestrator(mcp_client=mcp_client)

    # ---- Free-tier single-service mode: mount the MCP HTTP endpoints ----
    # directly in this Flask app (so http://<this-app>/mcp/rpc works too),
    # while the in-process MCPClient still uses the fast in-process path by
    # default. This satisfies "MCP server process may run within a single
    # deployed service" while still exposing a real HTTP MCP surface.
    if Config.MOUNT_MCP_IN_APP:
        from mcp_server.http_server import mcp_bp
        app.register_blueprint(mcp_bp)

    # ---- very small in-memory rate limiter (per-process; fine for a ----
    # single free-tier dyno; documented as a known scaling limitation) ----
    _request_log: dict[str, deque] = defaultdict(deque)

    def _rate_limited(ip: str) -> bool:
        now = time.time()
        window = _request_log[ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= Config.RATE_LIMIT_PER_MINUTE:
            return True
        window.append(now)
        return False

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    @app.get("/")
    def index():
        return render_template("index.html", llm_configured=bool(Config.LLM_API_KEY))

    @app.get("/health")
    def health():
        mcp_status = mcp_client.health()
        rag_ready = orchestrator.mcp.transport in ("inprocess", "http")
        return jsonify({
            "status": "ok",
            "app": "solarium-hr-assistant",
            "mcp": mcp_status,
            "llm_configured": bool(Config.LLM_API_KEY),
        })

    @app.post("/chat")
    def chat():
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
        if _rate_limited(ip):
            return jsonify({"error": "Rate limit exceeded. Please wait a moment and try again."}), 429

        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", ""))[: Config.MAX_MESSAGE_LENGTH]
        employee_id = payload.get("employee_id") or None
        confirm = bool(payload.get("confirm", False))
        pending_action = payload.get("pending_action") or None

        if not message and not (confirm and pending_action):
            return jsonify({"error": "Message is required."}), 400

        t0 = time.time()
        try:
            response = orchestrator.handle(
                message=message, employee_id=employee_id,
                confirm=confirm, pending_action=pending_action,
            )
        except Exception as exc:  # pragma: no cover - defensive top-level guard
            app.logger.exception("Unhandled error in orchestrator.handle")
            return jsonify({"error": "Something went wrong processing that request.", "detail": str(exc)}), 500

        latency_ms = round((time.time() - t0) * 1000, 2)
        return jsonify({
            "answer": response.answer,
            "workflow": response.workflow,
            "citations": response.citations,
            "trace": response.trace,
            "pending_action": response.pending_action,
            "clarification_needed": response.clarification_needed,
            "escalated": response.escalated,
            "latency_ms": latency_ms,
        })

    @app.get("/api/demo-tasks")
    def demo_tasks():
        """The >=2 reproducible agentic demo tasks required by the project
        spec, exposed as data so the UI can offer one-click "run demo"
        buttons and so a grader/API client can reproduce them exactly."""
        return jsonify({
            "tasks": [
                {
                    "id": "demo-1-remote-work",
                    "title": "Remote work eligibility (multi-step workflow)",
                    "message": "Can I work remotely from Portugal for a month?",
                    "employee_id": "EMP-0006",
                    "expected_tools": ["search_policy_documents", "lookup_employee_profile"],
                },
                {
                    "id": "demo-2-pto-request",
                    "title": "PTO request guidance (multi-step workflow)",
                    "message": "I want to take 2 weeks of PTO in October, what do I need to know?",
                    "employee_id": "EMP-0010",
                    "expected_tools": ["check_pto_balance", "search_policy_documents"],
                },
                {
                    "id": "demo-3-ticket-action",
                    "title": "Mock HR ticket creation (confirm-then-act)",
                    "message": "My laptop screen cracked, can you open an IT ticket?",
                    "employee_id": "EMP-0010",
                    "expected_tools": ["create_mock_hr_ticket"],
                    "requires_confirmation": True,
                },
            ]
        })

    @app.get("/api/sample-employees")
    def sample_employees():
        """A handful of employee IDs from the mock dataset for the UI's
        'try as' dropdown -- purely a UX convenience, not sensitive data."""
        from mcp_server.mock_data_store import get_store
        store = get_store()
        sample = list(store.employees.values())[:8]
        return jsonify([
            {"employee_id": e["employee_id"], "name": f"{e['first_name']} {e['last_name']}", "title": e["title"]}
            for e in sample
        ])

    # ---- basic security headers on every response ----
    @app.after_request
    def set_security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    return app


# WSGI entrypoint (`flask run`, gunicorn, and most PaaS buildpacks look for
# a module-level `app`).
app = create_app()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=Config.DEBUG)
