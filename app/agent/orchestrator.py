"""
app/agent/orchestrator.py
----------------------------
The agent orchestrator: interprets user intent, decides whether retrieval
alone is enough or MCP tools are needed, calls tools through the MCP client
layer, synthesizes a grounded final answer, and returns a concise
operational trace (never hidden chain-of-thought -- just "which tool, with
what arguments, with what result").

Orchestration approach: deterministic, rule-based intent routing rather than
a general-purpose agent framework (e.g. LangChain/AutoGPT-style free-form
tool loop). See design-and-evaluation.md "Agent Framework Choice" for the
full justification; in short: for a fixed, well-known set of 8 HR tools,
rule-based routing is fully deterministic (reproducible evaluation runs),
auditable (every branch is a readable if/elif, not an opaque LLM decision),
and works even when no LLM API key is configured (offline mode) -- while
still using the LLM (when available) for the part that benefits most from
it: turning retrieved evidence into a natural-language, well-cited answer.

Workflows implemented (>= 2 required):
  1. remote_work_eligibility  -- "Can I work from Portugal for a month?"
  2. pto_request_guidance      -- "I want to take 2 weeks off in October"
  3. benefits_question         -- "What's my dental coverage?"
  4. expense_compliance        -- "Can I expense a $90 client dinner?"
  5. onboarding_checklist      -- "What do I need to do in my first week?"
  6. hr_ticket_action           -- "Open an IT ticket for my broken laptop"
     (mock action tool, gated behind explicit user confirmation)
  7. draft_email_action         -- "Draft an email asking for parental leave"
     (mock action tool, gated behind explicit user confirmation)
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .guardrails import (
    has_sufficient_evidence,
    insufficient_evidence_message,
    is_in_scope,
    out_of_scope_message,
    requires_confirmation,
)
from .llm import LLMClient, LLMDisabledError, LLMError
from .prompts import ANSWER_USER_TEMPLATE, SYSTEM_PROMPT, format_policy_context, format_tool_context
from ..mcp_client import MCPClient, MCPToolUnavailableError


@dataclass
class TraceStep:
    step: str                     # short label, e.g. "retrieve_policy", "call_tool"
    detail: str                    # human-readable summary of what happened
    tool_name: str | None = None
    tool_arguments: dict | None = None
    tool_ok: bool | None = None
    latency_ms: float | None = None


@dataclass
class AgentResponse:
    answer: str
    workflow: str
    citations: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    pending_action: dict | None = None       # set when a mock action needs confirmation
    clarification_needed: bool = False
    escalated: bool = False


# ---------------------------------------------------------------------------
# Intent classification (deterministic keyword rules -- see module docstring)
# ---------------------------------------------------------------------------
EMPLOYEE_ID_RE = re.compile(r"\bEMP-\d{3,6}\b", re.IGNORECASE)
CONFIRM_PHRASES = {"yes", "confirm", "go ahead", "do it", "please do", "yes please", "confirmed", "sure, do it"}


def _extract_employee_id(text: str) -> str | None:
    m = EMPLOYEE_ID_RE.search(text)
    return m.group(0).upper() if m else None


def classify_intent(message: str) -> str:
    q = message.lower()

    if not is_in_scope(message):
        return "out_of_scope"

    if any(p in q for p in ["remote work eligib", "work remotely", "work from another country",
                              "work from home permanently", "hybrid schedule", "in-office days"]):
        return "remote_work_eligibility"

    if any(p in q for p in ["take pto", "request pto", "take time off", "book vacation",
                              "days off", "request time off", "how much pto do i have",
                              "pto balance", "vacation balance"]):
        return "pto_request_guidance"
    if "pto" in q and any(p in q for p in ["take", "request", "book", "need to know", "how much"]):
        return "pto_request_guidance"
    if "vacation" in q and any(p in q for p in ["take", "request", "book"]):
        return "pto_request_guidance"

    if any(p in q for p in ["benefits", "health plan", "dental", "vision", "401", "retirement",
                              "fsa", "life insurance", "wellness stipend"]):
        return "benefits_question"

    if any(p in q for p in ["can i expense", "is this expense", "expense compliant",
                              "reimburse", "within policy", "expense cap", "meal limit"]):
        return "expense_compliance"

    if any(p in q for p in ["onboarding checklist", "first week", "first day", "new hire",
                              "30/60/90", "what do i need to do when i start"]):
        return "onboarding_checklist"

    if any(p in q for p in ["open a ticket", "create a ticket", "file a ticket", "submit a ticket",
                              "report my laptop", "it ticket", "hr ticket"]):
        return "hr_ticket_action"

    if any(p in q for p in ["draft an email", "draft email", "write an email", "compose an email"]):
        return "draft_email_action"

    if any(p in q for p in ["who is my manager", "my profile", "my department", "my title",
                              "employee profile", "look up employee"]):
        return "employee_lookup"

    return "policy_qa"


class AgentOrchestrator:
    def __init__(self, mcp_client: MCPClient | None = None, llm_client: LLMClient | None = None):
        self.mcp = mcp_client or MCPClient()
        self.llm = llm_client or LLMClient()

    # -----------------------------------------------------------------
    def handle(self, message: str, employee_id: str | None = None,
               confirm: bool = False, pending_action: dict | None = None) -> AgentResponse:
        trace: list[TraceStep] = []
        message = (message or "").strip()

        if not message and not (confirm and pending_action):
            return AgentResponse(
                answer="I didn't receive a question -- what would you like to know?",
                workflow="clarification", clarification_needed=True,
                trace=[asdict_step(TraceStep("input_check", "Empty message received."))],
            )

        # ---- Resume a pending mock action if the user just confirmed it ----
        if confirm and pending_action:
            return self._execute_confirmed_action(pending_action, trace)

        employee_id = employee_id or _extract_employee_id(message)
        intent = classify_intent(message)
        trace.append(TraceStep("classify_intent", f"Classified as '{intent}'."))

        handler = {
            "out_of_scope": self._handle_out_of_scope,
            "remote_work_eligibility": self._handle_remote_work_eligibility,
            "pto_request_guidance": self._handle_pto_request_guidance,
            "benefits_question": self._handle_benefits_question,
            "expense_compliance": self._handle_expense_compliance,
            "onboarding_checklist": self._handle_onboarding_checklist,
            "hr_ticket_action": self._handle_ticket_action,
            "draft_email_action": self._handle_draft_email_action,
            "employee_lookup": self._handle_employee_lookup,
            "policy_qa": self._handle_policy_qa,
        }[intent]

        return handler(message, employee_id, trace)

    # -----------------------------------------------------------------
    # Shared helpers
    # -----------------------------------------------------------------
    def _call_tool(self, trace: list[TraceStep], tool_name: str, arguments: dict) -> dict | None:
        """Call an MCP tool through the MCP client, log a trace step, and
        return the result dict (or None on failure -- caller decides how to
        degrade gracefully)."""
        t0 = time.time()
        try:
            result = self.mcp.call_tool(tool_name, arguments)
        except MCPToolUnavailableError as exc:
            trace.append(TraceStep(
                "call_tool", f"MCP tool '{tool_name}' unavailable: {exc}",
                tool_name=tool_name, tool_arguments=arguments, tool_ok=False,
                latency_ms=round((time.time() - t0) * 1000, 2),
            ))
            return None

        ok = result.get("ok", False)
        summary = _summarize_tool_result(tool_name, result)
        trace.append(TraceStep(
            "call_tool", summary, tool_name=tool_name, tool_arguments=arguments,
            tool_ok=ok, latency_ms=result.get("latency_ms"),
        ))
        return result.get("result") if ok else None

    def _retrieve(self, trace: list[TraceStep], query: str, k: int = 5,
                   doc_id: str | None = None) -> list[dict]:
        args = {"query": query, "k": k}
        if doc_id:
            args["doc_id"] = doc_id
        data = self._call_tool(trace, "search_policy_documents", args)
        return data["results"] if data else []

    def _synthesize(self, query: str, policy_results: list[dict], tool_results: list[dict],
                     trace: list[TraceStep]) -> str:
        """Turn retrieved evidence into a final answer -- via the LLM if
        configured, else a deterministic offline template."""
        try:
            user_prompt = ANSWER_USER_TEMPLATE.format(
                query=query,
                policy_context=format_policy_context(policy_results),
                tool_context=format_tool_context(tool_results),
            )
            answer = self.llm.complete(SYSTEM_PROMPT, user_prompt)
            trace.append(TraceStep("synthesize_answer", f"Generated answer via LLM ({self.llm.model})."))
            return answer
        except LLMDisabledError:
            trace.append(TraceStep("synthesize_answer", "No LLM configured -- using offline template synthesis."))
            return _offline_synthesize(query, policy_results, tool_results)
        except LLMError as exc:
            trace.append(TraceStep("synthesize_answer", f"LLM call failed ({exc}); falling back to offline template."))
            return _offline_synthesize(query, policy_results, tool_results)

    @staticmethod
    def _citations(policy_results: list[dict]) -> list[dict]:
        return [
            {"doc_id": r["doc_id"], "doc_title": r.get("doc_title", ""),
             "section": r["section"], "snippet": r["snippet"]}
            for r in policy_results
        ]

    # -----------------------------------------------------------------
    # Intent handlers
    # -----------------------------------------------------------------
    def _handle_out_of_scope(self, message, employee_id, trace):
        trace.append(TraceStep("guardrail", "Query judged out of corpus scope; declining and redirecting."))
        return AgentResponse(answer=out_of_scope_message(), workflow="out_of_scope",
                              trace=steps(trace), escalated=False)

    def _handle_policy_qa(self, message, employee_id, trace):
        results = self._retrieve(trace, message, k=5)
        if not has_sufficient_evidence(results):
            trace.append(TraceStep("guardrail", "Retrieval confidence too low -- declining rather than guessing."))
            return AgentResponse(answer=insufficient_evidence_message(message), workflow="policy_qa",
                                  trace=steps(trace), citations=[])
        docs_covered = {r["doc_id"] for r in results}
        if len(docs_covered) > 1:
            trace.append(TraceStep("note", f"Answer synthesized from {len(docs_covered)} documents: {sorted(docs_covered)}."))
        answer = self._synthesize(message, results, [], trace)
        return AgentResponse(answer=answer, workflow="policy_qa", citations=self._citations(results), trace=steps(trace))

    def _handle_employee_lookup(self, message, employee_id, trace):
        if not employee_id:
            trace.append(TraceStep("clarify", "No employee_id found in message or request context."))
            return AgentResponse(
                answer="I can look that up -- what's your employee ID (e.g. EMP-0012)?",
                workflow="employee_lookup", clarification_needed=True, trace=steps(trace),
            )
        profile = self._call_tool(trace, "lookup_employee_profile", {"employee_id": employee_id})
        if not profile or not profile.get("found"):
            return AgentResponse(
                answer=f"I couldn't find an employee record for '{employee_id}'. Double-check the ID and try again.",
                workflow="employee_lookup", trace=steps(trace),
            )
        answer = (
            f"**{profile['name']}** -- {profile['title']}, {profile['department']}\n"
            f"- Manager: {profile['manager_name'] or 'none on record (executive/leadership)'}\n"
            f"- Work model: {profile['work_model']} · Office: {profile['office']}\n"
            f"- Employment type: {profile['employment_type']} · Tenure band: {profile['tenure_band']}\n"
            f"- Status: {profile['status']}"
        )
        return AgentResponse(answer=answer, workflow="employee_lookup", trace=steps(trace))

    def _handle_remote_work_eligibility(self, message, employee_id, trace):
        """Multi-step workflow #1: remote work eligibility.
        Steps: (1) retrieve SOL-OPS-201 policy evidence, (2) if we know the
        employee, look up their current work model/office for context,
        (3) synthesize eligibility guidance grounded in both."""
        results = self._retrieve(trace, message + " work model eligibility remote hybrid", k=5,
                                   doc_id="SOL-OPS-201")
        if not results:
            results = self._retrieve(trace, message, k=5)  # fall back to unscoped search

        profile = None
        if employee_id:
            profile = self._call_tool(trace, "lookup_employee_profile", {"employee_id": employee_id})

        if not has_sufficient_evidence(results):
            return AgentResponse(answer=insufficient_evidence_message(message), workflow="remote_work_eligibility",
                                  trace=steps(trace))

        tool_results = []
        if profile and profile.get("found"):
            tool_results.append({"tool_name": "lookup_employee_profile", "result": profile})

        answer = self._synthesize(message, results, tool_results, trace)
        return AgentResponse(answer=answer, workflow="remote_work_eligibility",
                              citations=self._citations(results), trace=steps(trace))

    def _handle_pto_request_guidance(self, message, employee_id, trace):
        """Multi-step workflow #2: PTO request guidance.
        Steps: (1) check_pto_balance for the employee (if known), (2)
        retrieve SOL-HR-101 request/approval process rules, (3) synthesize
        guidance that combines the employee's actual balance with the
        policy's notice/approval requirements."""
        balance = None
        if employee_id:
            balance = self._call_tool(trace, "check_pto_balance", {"employee_id": employee_id})

        results = self._retrieve(trace, "PTO request notice approval process " + message, k=5,
                                   doc_id="SOL-HR-101")
        if not results:
            results = self._retrieve(trace, message, k=5)

        if not has_sufficient_evidence(results) and not balance:
            return AgentResponse(answer=insufficient_evidence_message(message), workflow="pto_request_guidance",
                                  trace=steps(trace))

        if not employee_id:
            trace.append(TraceStep("note", "No employee_id provided -- answering with general policy guidance only."))

        tool_results = [{"tool_name": "check_pto_balance", "result": balance}] if balance else []
        answer = self._synthesize(message, results, tool_results, trace)
        return AgentResponse(answer=answer, workflow="pto_request_guidance",
                              citations=self._citations(results), trace=steps(trace))

    def _handle_benefits_question(self, message, employee_id, trace):
        status = None
        if employee_id:
            status = self._call_tool(trace, "lookup_benefits_status", {"employee_id": employee_id})
        results = self._retrieve(trace, message, k=5, doc_id="SOL-HR-103")
        if not results:
            results = self._retrieve(trace, message, k=5)
        if not has_sufficient_evidence(results) and not status:
            return AgentResponse(answer=insufficient_evidence_message(message), workflow="benefits_question",
                                  trace=steps(trace))
        tool_results = [{"tool_name": "lookup_benefits_status", "result": status}] if status else []
        answer = self._synthesize(message, results, tool_results, trace)
        return AgentResponse(answer=answer, workflow="benefits_question",
                              citations=self._citations(results), trace=steps(trace))

    def _handle_expense_compliance(self, message, employee_id, trace):
        amount = _extract_dollar_amount(message)
        topic = message
        compliance = self._call_tool(trace, "check_policy_compliance",
                                       {"topic": topic, "amount": amount} if amount is not None else {"topic": topic})
        results = self._retrieve(trace, message, k=4, doc_id="SOL-FIN-301")
        if not results:
            results = self._retrieve(trace, message, k=4)
        tool_results = [{"tool_name": "check_policy_compliance", "result": compliance}] if compliance else []
        answer = self._synthesize(message, results, tool_results, trace)
        return AgentResponse(answer=answer, workflow="expense_compliance",
                              citations=self._citations(results), trace=steps(trace))

    def _handle_onboarding_checklist(self, message, employee_id, trace):
        results = self._retrieve(trace, "onboarding checklist first week 30 60 90 day plan " + message, k=6,
                                   doc_id="SOL-HR-104")
        if not results:
            results = self._retrieve(trace, message, k=6)
        profile = None
        if employee_id:
            profile = self._call_tool(trace, "lookup_employee_profile", {"employee_id": employee_id})
        tool_results = [{"tool_name": "lookup_employee_profile", "result": profile}] if profile and profile.get("found") else []
        answer = self._synthesize(message, results, tool_results, trace)
        return AgentResponse(answer=answer, workflow="onboarding_checklist",
                              citations=self._citations(results), trace=steps(trace))

    def _handle_ticket_action(self, message, employee_id, trace):
        """Action workflow: create_mock_hr_ticket. Irreversible-action
        guardrail: never calls the tool on the first pass -- always returns
        a `pending_action` for the UI to show a confirm button, and only
        executes once `confirm=True` is sent back (see handle())."""
        if not employee_id:
            trace.append(TraceStep("clarify", "Ticket creation requires an employee_id; none provided."))
            return AgentResponse(
                answer="I can open that ticket, but I need your employee ID first (e.g. EMP-0012).",
                workflow="hr_ticket_action", clarification_needed=True, trace=steps(trace),
            )
        category, priority = _infer_ticket_category(message)
        pending = {
            "tool_name": "create_mock_hr_ticket",
            "arguments": {
                "employee_id": employee_id,
                "category": category,
                "subject": message[:120],
                "description": message,
                "priority": priority,
            },
        }
        trace.append(TraceStep(
            "await_confirmation",
            f"Prepared a MOCK '{category}' ticket (priority {priority}) but did not create it -- "
            "waiting for explicit user confirmation before this action-tool is called.",
        ))
        return AgentResponse(
            answer=(f"I can open a **{category}** ticket (priority: {priority}) with this description:\n\n"
                    f"> {message}\n\nThis is a mock action for demo purposes -- no real ticketing system is "
                    f"contacted. Reply \u201cconfirm\u201d to create it, or tell me what to change first."),
            workflow="hr_ticket_action", pending_action=pending, trace=steps(trace),
        )

    def _handle_draft_email_action(self, message, employee_id, trace):
        if not employee_id:
            trace.append(TraceStep("clarify", "Email drafting requires an employee_id; none provided."))
            return AgentResponse(
                answer="I can draft that -- what's your employee ID (e.g. EMP-0012)?",
                workflow="draft_email_action", clarification_needed=True, trace=steps(trace),
            )
        pending = {
            "tool_name": "draft_hr_email",
            "arguments": {"employee_id": employee_id, "purpose": message},
        }
        trace.append(TraceStep(
            "await_confirmation",
            "Prepared a MOCK email draft request but did not draft it -- waiting for explicit user confirmation.",
        ))
        return AgentResponse(
            answer=(f"I can draft an email about: \u201c{message}\u201d. This only produces text for you to review "
                    f"and send yourself -- nothing is ever sent automatically. Reply \u201cconfirm\u201d to generate the draft."),
            workflow="draft_email_action", pending_action=pending, trace=steps(trace),
        )

    def _execute_confirmed_action(self, pending_action: dict, trace: list[TraceStep]) -> AgentResponse:
        tool_name = pending_action.get("tool_name")
        arguments = pending_action.get("arguments", {})
        if not requires_confirmation(tool_name):
            trace.append(TraceStep("guardrail", f"'{tool_name}' is not a recognized confirmable action tool."))
            return AgentResponse(answer="I couldn't confirm that action -- please try again.",
                                  workflow="action_error", trace=steps(trace))

        result = self._call_tool(trace, tool_name, arguments)
        if result is None:
            return AgentResponse(
                answer="Sorry -- that action failed. Please try again in a moment, or contact "
                       "people-ops@solarium.example if it keeps happening.",
                workflow="action_error", trace=steps(trace),
            )

        if tool_name == "create_mock_hr_ticket":
            t = result["ticket"]
            answer = (f"Done -- mock ticket **{t['ticket_id']}** created "
                      f"({t['category']}, priority {t['priority']}, status {t['status']}). "
                      f"This is a simulated write for demo purposes; no real ticketing system was contacted.")
        elif tool_name == "draft_hr_email":
            answer = f"Here's the draft (not sent):\n\n```\n{result['email_draft']}\n```"
        else:  # pragma: no cover
            answer = f"Action '{tool_name}' completed: {result}"

        return AgentResponse(answer=answer, workflow="action_confirmed", trace=steps(trace))


# ---------------------------------------------------------------------------
# module-level helpers
# ---------------------------------------------------------------------------
def asdict_step(step: TraceStep) -> dict:
    return {
        "step": step.step, "detail": step.detail, "tool_name": step.tool_name,
        "tool_arguments": step.tool_arguments, "tool_ok": step.tool_ok,
        "latency_ms": step.latency_ms,
    }


def steps(trace: list[TraceStep]) -> list[dict]:
    return [asdict_step(s) for s in trace]


def _summarize_tool_result(tool_name: str, result: dict) -> str:
    if not result.get("ok"):
        return f"Tool '{tool_name}' failed: {result.get('error')}"
    payload = result.get("result") or {}
    if tool_name == "search_policy_documents":
        return f"Retrieved {payload.get('result_count', 0)} chunk(s) from {payload.get('documents_covered')}."
    if tool_name in ("lookup_employee_profile", "check_pto_balance", "lookup_benefits_status"):
        found = payload.get("found")
        return f"Looked up {tool_name.replace('_', ' ')}: {'found' if found else 'not found'}."
    if tool_name == "check_policy_compliance":
        return f"Compliance verdict: {payload.get('verdict')}."
    if tool_name == "create_mock_hr_ticket":
        return f"Created mock ticket {payload.get('ticket', {}).get('ticket_id')}."
    if tool_name == "draft_hr_email":
        return "Drafted mock email."
    return f"Tool '{tool_name}' returned a result."


_DOLLAR_RE = re.compile(r"\$\s?(\d+(?:\.\d{1,2})?)")


def _extract_dollar_amount(text: str) -> float | None:
    m = _DOLLAR_RE.search(text)
    return float(m.group(1)) if m else None


def _infer_ticket_category(message: str) -> tuple[str, str]:
    q = message.lower()
    if any(w in q for w in ["laptop", "monitor", "vpn", "password", "software", "hardware", "wifi", "wi-fi"]):
        return "IT", "Medium"
    if any(w in q for w in ["phishing", "stolen", "lost device", "breach", "suspicious"]):
        return "Security", "High"
    if any(w in q for w in ["badge", "desk", "office", "conference room"]):
        return "Facilities", "Low"
    return "HR", "Medium"


def _offline_synthesize(query: str, policy_results: list[dict], tool_results: list[dict]) -> str:
    """Deterministic, template-based answer composition used when no LLM is
    configured. Produces a genuinely grounded, cited answer -- just without
    an LLM's natural-language rewrite -- so the whole system is usable and
    evaluable with zero API cost."""
    lines = []
    if tool_results:
        lines.append("**From your records:**")
        for t in tool_results:
            res = t["result"]
            if not res:
                continue
            if t["tool_name"] == "check_pto_balance" and res.get("found"):
                lines.append(
                    f"- PTO balance: {res['pto_balance_days']} days · "
                    f"Sick leave: {res['sick_leave_balance_hours']} hours · "
                    f"Floating holidays remaining: {res['floating_holidays_remaining']} "
                    f"(as of {res['as_of_date']})"
                )
            elif t["tool_name"] == "lookup_benefits_status" and res.get("found"):
                lines.append(
                    f"- Health plan: {res.get('health_plan')} · Dental: {res.get('dental')} · "
                    f"Vision: {res.get('vision')} · Retirement contribution: {res.get('retirement_contribution_pct')}%"
                )
            elif t["tool_name"] == "lookup_employee_profile" and res.get("found"):
                lines.append(f"- {res['name']} · {res['title']} · {res['work_model']} · {res['office']}")
            elif t["tool_name"] == "check_policy_compliance":
                lines.append(f"- Compliance check for '{res.get('topic')}': **{res.get('verdict')}** -- {res.get('reason')}")
        lines.append("")

    if policy_results:
        lines.append("**Relevant policy:**")
        for r in policy_results[:4]:
            lines.append(f"- ({r['doc_id']}, {r['section']}): {r['snippet']}")
    else:
        lines.append("I found your records above, but no directly matching policy section for the wording used --"
                      " try rephrasing with more specific policy terms if you need the exact rule text.")

    return "\n".join(lines).strip()
