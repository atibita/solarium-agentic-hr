"""
tests/test_agent.py
----------------------
Verifies the agent orchestrator: intent routing, multi-step workflows,
grounded citations, out-of-scope refusal, missing-employee-ID clarification,
and the confirm-then-act gate for irreversible mock actions.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agent.orchestrator import AgentOrchestrator  # noqa: E402


class AgentWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = AgentOrchestrator()

    def test_simple_policy_question_is_grounded_and_cited(self):
        r = self.agent.handle("How many days of bereavement leave do I get?")
        self.assertEqual(r.workflow, "policy_qa")
        self.assertTrue(r.citations)
        self.assertTrue(any(c["doc_id"] == "SOL-HR-101" for c in r.citations))

    def test_multi_step_workflow_remote_work_eligibility(self):
        r = self.agent.handle("Can I work remotely from Portugal for a month?", employee_id="EMP-0006")
        self.assertEqual(r.workflow, "remote_work_eligibility")
        tool_names = [s["tool_name"] for s in r.trace if s["tool_name"]]
        self.assertIn("search_policy_documents", tool_names)
        self.assertIn("lookup_employee_profile", tool_names)

    def test_multi_step_workflow_pto_request_guidance(self):
        r = self.agent.handle("I want to take 2 weeks of PTO in October, what do I need to know?",
                                employee_id="EMP-0010")
        self.assertEqual(r.workflow, "pto_request_guidance")
        tool_names = [s["tool_name"] for s in r.trace if s["tool_name"]]
        self.assertIn("check_pto_balance", tool_names)
        self.assertIn("search_policy_documents", tool_names)

    def test_out_of_scope_question_is_declined(self):
        r = self.agent.handle("What's the weather like today?")
        self.assertEqual(r.workflow, "out_of_scope")
        self.assertIn("outside what I can help with", r.answer)

    def test_ticket_action_without_employee_id_asks_for_clarification(self):
        r = self.agent.handle("Open an IT ticket, my laptop screen is cracked")
        self.assertTrue(r.clarification_needed)
        self.assertIsNone(r.pending_action)

    def test_ticket_action_requires_confirmation_before_executing(self):
        r = self.agent.handle("Open an IT ticket, my laptop screen is cracked", employee_id="EMP-0010")
        self.assertIsNotNone(r.pending_action)
        self.assertEqual(r.pending_action["tool_name"], "create_mock_hr_ticket")
        # The tool must NOT have been called yet -- no ticket-creation trace step.
        tool_names = [s["tool_name"] for s in r.trace if s["tool_name"]]
        self.assertNotIn("create_mock_hr_ticket", tool_names)

    def test_confirming_pending_action_executes_the_tool(self):
        first = self.agent.handle("Open an IT ticket, my laptop screen is cracked", employee_id="EMP-0010")
        second = self.agent.handle("", confirm=True, pending_action=first.pending_action)
        self.assertEqual(second.workflow, "action_confirmed")
        self.assertIn("TCK-", second.answer)

    def test_ambiguous_empty_message_asks_for_clarification(self):
        r = self.agent.handle("")
        self.assertTrue(r.clarification_needed)

    def test_multi_document_question_cites_more_than_one_policy(self):
        r = self.agent.handle(
            "If a company holiday falls during my parental leave, is it paid, "
            "and does it affect my PTO carryover cap?"
        )
        doc_ids = {c["doc_id"] for c in r.citations}
        self.assertGreaterEqual(len(doc_ids), 2)


if __name__ == "__main__":
    unittest.main()
