"""
mcp_server/tool_registry.py
-----------------------------
A minimal, dependency-free implementation of the two MCP primitives our
agent actually needs: `tools/list` (tool discovery with JSON-Schema
argument definitions) and `tools/call` (invoke a named tool with validated
arguments, get back a structured result).

Why a custom registry instead of the official `mcp` PyPI package?
See design-and-evaluation.md, "MCP Transport Choice", for the full
rationale. Summary: the official SDK is fully supported (see
mcp_server/official_sdk_server.py for a drop-in FastMCP version), but this
registry lets the exact same tool implementations be:
  1. exposed over HTTP using MCP's JSON-RPC 2.0 message shape
     (methods "tools/list" / "tools/call") -- see http_server.py, and
  2. imported and called in-process for fast, dependency-free unit tests
     and for local dev without spawning a second process
without duplicating a single line of tool logic. Both paths funnel through
`ToolRegistry.call_tool()`, so the agent is always going *through* the MCP
tool layer's schema validation and never calling a tool's Python function
directly -- satisfying "hard-coded direct function calls are not
sufficient unless wrapped and invoked through the MCP layer."
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable


class MCPToolError(Exception):
    """Raised when a tool call fails validation or execution."""
    def __init__(self, message: str, code: str = "tool_error"):
        super().__init__(message)
        self.code = code


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict            # JSON Schema for arguments
    handler: Callable[..., dict]  # python callable(**kwargs) -> dict result
    readonly: bool = True         # False for tools with side effects (mock writes)


@dataclass
class ToolCallResult:
    tool_name: str
    arguments: dict
    ok: bool
    result: Any = None
    error: str | None = None
    latency_ms: float = 0.0


class ToolRegistry:
    """In-process MCP-style tool registry. One instance = one 'MCP server'."""

    def __init__(self, server_name: str):
        self.server_name = server_name
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def list_tools(self) -> list[dict]:
        """Equivalent of the MCP 'tools/list' response."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
                "readonly": t.readonly,
            }
            for t in self._tools.values()
        ]

    def _validate(self, tool: MCPTool, arguments: dict) -> None:
        """Lightweight JSON-Schema-style validation: required fields present,
        no unknown top-level fields. Enough to catch the failure modes an
        agent actually needs to handle (missing employee_id, typo'd field
        names) without a full jsonschema dependency."""
        schema = tool.input_schema
        required = schema.get("required", [])
        props = schema.get("properties", {})
        missing = [f for f in required if f not in arguments or arguments[f] in (None, "")]
        if missing:
            raise MCPToolError(
                f"Missing required argument(s) for '{tool.name}': {', '.join(missing)}",
                code="missing_arguments",
            )
        unknown = [f for f in arguments if f not in props]
        if unknown:
            raise MCPToolError(
                f"Unknown argument(s) for '{tool.name}': {', '.join(unknown)}",
                code="unknown_arguments",
            )

    def call_tool(self, name: str, arguments: dict | None = None) -> ToolCallResult:
        """Equivalent of the MCP 'tools/call' request/response cycle."""
        arguments = arguments or {}
        t0 = time.time()
        tool = self._tools.get(name)
        if tool is None:
            return ToolCallResult(
                tool_name=name, arguments=arguments, ok=False,
                error=f"Unknown MCP tool '{name}'. Available: {', '.join(self._tools)}",
                latency_ms=round((time.time() - t0) * 1000, 2),
            )
        try:
            self._validate(tool, arguments)
            result = tool.handler(**arguments)
            return ToolCallResult(
                tool_name=name, arguments=arguments, ok=True, result=result,
                latency_ms=round((time.time() - t0) * 1000, 2),
            )
        except MCPToolError as exc:
            return ToolCallResult(
                tool_name=name, arguments=arguments, ok=False, error=str(exc),
                latency_ms=round((time.time() - t0) * 1000, 2),
            )
        except Exception as exc:  # pragma: no cover - defensive catch-all
            traceback.print_exc()
            return ToolCallResult(
                tool_name=name, arguments=arguments, ok=False,
                error=f"Internal error executing '{name}': {exc}",
                latency_ms=round((time.time() - t0) * 1000, 2),
            )
