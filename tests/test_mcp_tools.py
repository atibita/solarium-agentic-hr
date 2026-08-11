"""
tests/test_mcp_tools.py
--------------------------
Verifies MCP tool discovery ('tools/list' equivalent) and tool invocation
('tools/call' equivalent) for both the in-process registry and the HTTP
transport, satisfying the CI/CD requirement for "at least one test or
script that verifies MCP tool discovery or a simple MCP tool call."
"""
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp_server.server import get_registry  # noqa: E402
from mcp_server.http_server import create_standalone_app  # noqa: E402
from app.mcp_client import MCPClient  # noqa: E402

REQUIRED_TOOLS = {
    "search_policy_documents", "get_policy_section", "check_policy_compliance",
    "lookup_employee_profile", "check_pto_balance", "lookup_benefits_status",
    "create_mock_hr_ticket", "draft_hr_email",
}


class InProcessRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = get_registry()

    def test_tool_discovery_exposes_at_least_five_tools(self):
        tools = self.registry.list_tools()
        names = {t["name"] for t in tools}
        self.assertGreaterEqual(len(names), 5)
        self.assertTrue(REQUIRED_TOOLS.issubset(names))

    def test_at_least_one_tool_uses_rag_index(self):
        result = self.registry.call_tool("search_policy_documents", {"query": "PTO carryover", "k": 3})
        self.assertTrue(result.ok)
        self.assertIn("results", result.result)

    def test_at_least_one_tool_uses_mock_structured_data(self):
        result = self.registry.call_tool("check_pto_balance", {"employee_id": "EMP-0006"})
        self.assertTrue(result.ok)
        self.assertTrue(result.result["found"])

    def test_mock_ticket_creation_is_a_simulated_write(self):
        result = self.registry.call_tool("create_mock_hr_ticket", {
            "employee_id": "EMP-0006", "category": "IT", "subject": "Test ticket from CI",
        })
        self.assertTrue(result.ok)
        self.assertTrue(result.result["mock_action"])
        self.assertTrue(result.result["ticket"]["ticket_id"].startswith("TCK-"))

    def test_missing_required_argument_fails_cleanly(self):
        result = self.registry.call_tool("check_pto_balance", {})
        self.assertFalse(result.ok)
        self.assertIn("employee_id", result.error)

    def test_unknown_tool_fails_cleanly(self):
        result = self.registry.call_tool("not_a_real_tool", {})
        self.assertFalse(result.ok)


class HttpTransportTests(unittest.TestCase):
    """Spins up the standalone MCP HTTP server on a background thread and
    exercises the same tool calls over real HTTP + JSON-RPC, proving the
    'separate service over HTTP' deployment mode works end-to-end."""

    @classmethod
    def setUpClass(cls):
        cls.port = 8711
        app = create_standalone_app()
        cls.server_thread = threading.Thread(
            target=lambda: app.run(host="127.0.0.1", port=cls.port, use_reloader=False),
            daemon=True,
        )
        cls.server_thread.start()
        time.sleep(1.0)  # give the dev server a moment to bind

    def setUp(self):
        self.client = MCPClient(transport="http", server_url=f"http://127.0.0.1:{self.port}")

    def test_http_tool_discovery(self):
        tools = self.client.list_tools()
        names = {t["name"] for t in tools}
        self.assertTrue(REQUIRED_TOOLS.issubset(names))

    def test_http_tool_call(self):
        result = self.client.call_tool("check_pto_balance", {"employee_id": "EMP-0006"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["found"])

    def test_http_health(self):
        health = self.client.health()
        self.assertTrue(health["connected"])
        self.assertEqual(health["transport"], "http")


if __name__ == "__main__":
    unittest.main()
