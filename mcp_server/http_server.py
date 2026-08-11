"""
mcp_server/http_server.py
----------------------------
Exposes the tool registry over HTTP using JSON-RPC 2.0 message shapes that
match MCP's `tools/list` and `tools/call` methods:

  POST /mcp/rpc
      {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
      {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
       "params": {"name": "check_pto_balance", "arguments": {"employee_id": "EMP-0007"}}}

  GET /mcp/health
      simple liveness probe used by the web app's own /health endpoint

This can run either:
  (a) as its own standalone process (`python -m mcp_server.run_http`), which
      is how it's deployed as a separate Render/Railway service, with the
      web app pointed at it via the MCP_SERVER_URL env var, or
  (b) mounted in-process behind the main Flask app (see app/main.py) for the
      single-service free-tier deployment mode.

Both modes serve byte-identical tool schemas and behavior because both call
`mcp_server.server.get_registry()`.
"""
from __future__ import annotations

from flask import Blueprint, Flask, jsonify, request

from .server import get_registry

mcp_bp = Blueprint("mcp", __name__, url_prefix="/mcp")


@mcp_bp.get("/health")
def mcp_health():
    registry = get_registry()
    return jsonify({
        "status": "ok",
        "server_name": registry.server_name,
        "tool_count": len(registry.list_tools()),
    })


@mcp_bp.post("/rpc")
def mcp_rpc():
    """Single JSON-RPC 2.0 endpoint handling 'tools/list' and 'tools/call'."""
    payload = request.get_json(silent=True) or {}
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    registry = get_registry()

    if method == "tools/list":
        return jsonify({
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": registry.list_tools()},
        })

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not name:
            return _jsonrpc_error(req_id, -32602, "Missing 'name' in params"), 400
        call = registry.call_tool(name, arguments)
        if not call.ok:
            return jsonify({
                "jsonrpc": "2.0", "id": req_id,
                "result": {"isError": True, "content": [{"type": "text", "text": call.error}]},
                "_meta": {"latency_ms": call.latency_ms},
            })
        return jsonify({
            "jsonrpc": "2.0", "id": req_id,
            "result": {"isError": False, "content": [{"type": "json", "json": call.result}]},
            "_meta": {"latency_ms": call.latency_ms},
        })

    return _jsonrpc_error(req_id, -32601, f"Unknown method '{method}'"), 404


def _jsonrpc_error(req_id, code: int, message: str):
    return jsonify({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def create_standalone_app() -> Flask:
    """Factory for running the MCP server as its own Flask process
    (separate free-tier service)."""
    app = Flask(__name__)
    app.register_blueprint(mcp_bp)

    @app.get("/")
    def index():
        return jsonify({"service": "solarium-mcp-server", "see": "/mcp/health, /mcp/rpc"})

    return app
