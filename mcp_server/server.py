"""
mcp_server/server.py
----------------------
Builds the Solarium MCP tool server: registers all 8 tools (3 policy/RAG
tools + 5 mock-structured-data tools) with their JSON-Schema argument
definitions onto a ToolRegistry.

This module is the single source of truth for tool schemas. Both the
in-process transport (used by tests and single-service deployments) and the
HTTP transport (http_server.py) build their registry by calling
`build_registry()`, so schema drift between transports is impossible.
"""
from __future__ import annotations

from .tool_registry import MCPTool, ToolRegistry
from .tools.policy_tools import (
    search_policy_documents,
    get_policy_section,
    check_policy_compliance,
)
from .tools.hr_data_tools import (
    lookup_employee_profile,
    check_pto_balance,
    lookup_benefits_status,
    create_mock_hr_ticket,
    draft_hr_email,
)

SERVER_NAME = "solarium-hr-tools"


def build_registry() -> ToolRegistry:
    registry = ToolRegistry(SERVER_NAME)

    # -------------------- RAG / policy-evidence tools ----------------------
    registry.register(MCPTool(
        name="search_policy_documents",
        description=(
            "Search the Solarium policy corpus (PTO, holidays, remote work, "
            "expenses, data security, benefits, onboarding, equipment, "
            "conduct) and return the top-k matching sections with citations."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language question or keywords"},
                "k": {"type": "integer", "description": "Number of results (default 5)"},
                "doc_id": {"type": "string", "description": "Optional Document ID to restrict search to"},
            },
            "required": ["query"],
        },
        handler=search_policy_documents,
        readonly=True,
    ))

    registry.register(MCPTool(
        name="get_policy_section",
        description="Fetch the full text of a specific section of a specific policy document.",
        input_schema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Canonical Document ID, e.g. SOL-HR-101"},
                "section": {"type": "string", "description": "Section title or substring"},
            },
            "required": ["document_id", "section"],
        },
        handler=get_policy_section,
        readonly=True,
    ))

    registry.register(MCPTool(
        name="check_policy_compliance",
        description=(
            "Check a proposed action/amount against retrieved policy rules "
            "(e.g. is a $90 meal within the $75/day travel meal cap)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "What to check, e.g. 'client meal expense'"},
                "amount": {"type": "number", "description": "Optional dollar amount to check"},
                "context": {"type": "string", "description": "Optional extra context"},
            },
            "required": ["topic"],
        },
        handler=check_policy_compliance,
        readonly=True,
    ))

    # -------------------- Mock structured HR data tools ---------------------
    registry.register(MCPTool(
        name="lookup_employee_profile",
        description="Look up a Solarium employee's profile (department, title, manager, office) by employee ID.",
        input_schema={
            "type": "object",
            "properties": {"employee_id": {"type": "string", "description": "e.g. EMP-0007"}},
            "required": ["employee_id"],
        },
        handler=lookup_employee_profile,
        readonly=True,
    ))

    registry.register(MCPTool(
        name="check_pto_balance",
        description="Look up an employee's current PTO, sick leave, and floating holiday balances.",
        input_schema={
            "type": "object",
            "properties": {"employee_id": {"type": "string", "description": "e.g. EMP-0007"}},
            "required": ["employee_id"],
        },
        handler=check_pto_balance,
        readonly=True,
    ))

    registry.register(MCPTool(
        name="lookup_benefits_status",
        description="Look up an employee's current benefits elections (health, dental, vision, retirement, FSA).",
        input_schema={
            "type": "object",
            "properties": {"employee_id": {"type": "string", "description": "e.g. EMP-0007"}},
            "required": ["employee_id"],
        },
        handler=lookup_benefits_status,
        readonly=True,
    ))

    registry.register(MCPTool(
        name="create_mock_hr_ticket",
        description=(
            "Create a MOCK HR/IT support ticket (simulated write, no real system contacted). "
            "Requires explicit user confirmation before being called by the agent."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "category": {"type": "string", "description": "IT | HR | Security | Facilities"},
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string", "description": "Low | Medium | High | Urgent"},
            },
            "required": ["employee_id", "category", "subject"],
        },
        handler=create_mock_hr_ticket,
        readonly=False,
    ))

    registry.register(MCPTool(
        name="draft_hr_email",
        description=(
            "Draft (never send) an HR-related email on the employee's behalf. "
            "Requires explicit user confirmation before being called by the agent."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "purpose": {"type": "string"},
                "key_points": {"type": "string", "description": "Optional comma-separated key points"},
            },
            "required": ["employee_id", "purpose"],
        },
        handler=draft_hr_email,
        readonly=False,
    ))

    return registry


# Module-level singleton registry, built once per process.
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = build_registry()
    return _registry
