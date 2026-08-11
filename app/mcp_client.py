"""
app/mcp_client.py
--------------------
The agent's MCP client: a single `call_tool(name, arguments)` interface
that the orchestrator uses for every tool call, regardless of transport.

Transport is chosen via the MCP_TRANSPORT env var:
  - "inprocess" (default): imports mcp_server.server.get_registry() directly
     and calls registry.call_tool(). Used for local dev and the free-tier
     "single service" deployment mode (web app + MCP server in one process --
     see app/main.py, which mounts the MCP Flask blueprint alongside the
     chat routes). Even in this mode, calls still go through the *same*
     ToolRegistry.call_tool() schema-validation layer that the HTTP
     transport uses -- so it is not a "hard-coded direct function call"
     bypassing the MCP tool layer, it's the identical MCP call path running
     in the same OS process instead of over a socket.
  - "http": calls a separately-deployed MCP server over HTTP using the
     JSON-RPC 2.0 "tools/call" method (see mcp_server/http_server.py).
     Configure the URL via MCP_SERVER_URL, e.g.
     MCP_SERVER_URL=https://solarium-mcp.onrender.com

This lets the exact same agent code run against an in-process registry in
CI/unit tests and against a real, independently-deployed MCP HTTP service
in production, with a one-line env var change.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class MCPToolUnavailableError(Exception):
    pass


class MCPClient:
    def __init__(self, transport: str | None = None, server_url: str | None = None, timeout: float = 10.0):
        self.transport = (transport or os.environ.get("MCP_TRANSPORT", "inprocess")).lower()
        self.server_url = (server_url or os.environ.get("MCP_SERVER_URL", "http://localhost:8001")).rstrip("/")
        self.timeout = timeout
        self._registry = None  # lazily imported for inprocess mode
        self._rpc_id = 0

    # -- public API -------------------------------------------------------
    def list_tools(self) -> list[dict]:
        if self.transport == "inprocess":
            return self._registry_singleton().list_tools()
        return self._http_rpc("tools/list", {})["result"]["tools"]

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Returns {"ok": bool, "result": dict|None, "error": str|None, "latency_ms": float}."""
        if self.transport == "inprocess":
            call = self._registry_singleton().call_tool(name, arguments)
            return {"ok": call.ok, "result": call.result, "error": call.error, "latency_ms": call.latency_ms}

        if self.transport == "http":
            try:
                resp = self._http_rpc("tools/call", {"name": name, "arguments": arguments})
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                raise MCPToolUnavailableError(f"MCP server at {self.server_url} unreachable: {exc}") from exc

            latency = resp.get("_meta", {}).get("latency_ms")
            result_block = resp.get("result", {})
            if result_block.get("isError"):
                error_text = result_block["content"][0]["text"] if result_block.get("content") else "unknown error"
                return {"ok": False, "result": None, "error": error_text, "latency_ms": latency}
            content = result_block.get("content", [])
            payload = content[0]["json"] if content else None
            return {"ok": True, "result": payload, "error": None, "latency_ms": latency}

        raise MCPToolUnavailableError(f"Unknown MCP_TRANSPORT '{self.transport}'")

    def health(self) -> dict:
        """Used by the web app's /health endpoint to report MCP connectivity."""
        try:
            tools = self.list_tools()
            return {"connected": True, "transport": self.transport, "tool_count": len(tools)}
        except Exception as exc:  # pragma: no cover - defensive
            return {"connected": False, "transport": self.transport, "error": str(exc)}

    # -- internals ----------------------------------------------------------
    def _registry_singleton(self):
        if self._registry is None:
            from mcp_server.server import get_registry
            self._registry = get_registry()
        return self._registry

    def _http_rpc(self, method: str, params: dict) -> dict:
        self._rpc_id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._rpc_id, "method": method, "params": params}).encode()
        req = urllib.request.Request(
            url=f"{self.server_url}/mcp/rpc", data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())
