"""
tests/test_health.py
-----------------------
Verifies the app can start and the /health endpoint reports both app and
MCP connectivity status. This is the "at least one automated test that
verifies the app can start" required by the project's CI/CD section.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import create_app  # noqa: E402


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_app_starts_and_health_ok(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["app"], "solarium-hr-assistant")
        self.assertIn("mcp", data)
        self.assertIn("connected", data["mcp"])

    def test_mcp_is_connected_in_default_inprocess_mode(self):
        resp = self.client.get("/health")
        data = resp.get_json()
        self.assertTrue(data["mcp"]["connected"])
        self.assertGreaterEqual(data["mcp"]["tool_count"], 5)

    def test_index_page_renders(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Solarium HR Assistant", resp.data)

    def test_demo_tasks_endpoint_returns_at_least_two_tasks(self):
        resp = self.client.get("/api/demo-tasks")
        self.assertEqual(resp.status_code, 200)
        tasks = resp.get_json()["tasks"]
        self.assertGreaterEqual(len(tasks), 2)


if __name__ == "__main__":
    unittest.main()
