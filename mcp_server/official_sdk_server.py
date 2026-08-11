"""
mcp_server/official_sdk_server.py
------------------------------------
OPTIONAL, NOT USED BY DEFAULT. This file shows how the exact same tool
implementations (mcp_server/tools/*.py) would be exposed using the official
`mcp` Python SDK (https://pypi.org/project/mcp/) instead of this project's
lightweight custom JSON-RPC HTTP registry (mcp_server/http_server.py).

Why isn't this the default? See design-and-evaluation.md, "MCP Transport
Choice", for the full rationale -- in short: the official SDK is an extra
dependency with its own event loop / stdio-framing requirements that are
harder to unit-test deterministically in a free-tier, zero-cost CI
environment, whereas the custom JSON-RPC-over-HTTP registry in
http_server.py implements the same two MCP primitives (tools/list,
tools/call) with the same message shapes, is dependency-free, and is fully
exercised by tests/test_mcp_tools.py against a real running HTTP server.

To use this instead: `pip install mcp`, then run:
    python -m mcp_server.official_sdk_server
and point MCP_TRANSPORT/MCP_SERVER_URL (or an MCP-SDK-based client) at it
per the official SDK's client documentation. Tool logic is unchanged --
only the transport/framing differs.
"""
from __future__ import annotations

# NOTE: requires `pip install mcp` (not in requirements.txt by default --
# see module docstring above).
try:
    from mcp.server.fastmcp import FastMCP  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'mcp' package is not installed. Run `pip install mcp` to use "
        "the official-SDK server variant (mcp_server/official_sdk_server.py). "
        "The default, dependency-free server is mcp_server/http_server.py."
    ) from exc

from .tools.hr_data_tools import (
    check_pto_balance,
    create_mock_hr_ticket,
    draft_hr_email,
    lookup_benefits_status,
    lookup_employee_profile,
)
from .tools.policy_tools import check_policy_compliance, get_policy_section, search_policy_documents

mcp = FastMCP("solarium-hr-tools")

# FastMCP infers each tool's JSON-Schema from the Python function signature
# and uses the docstring as the tool description, so registration is just:
mcp.tool()(search_policy_documents)
mcp.tool()(get_policy_section)
mcp.tool()(check_policy_compliance)
mcp.tool()(lookup_employee_profile)
mcp.tool()(check_pto_balance)
mcp.tool()(lookup_benefits_status)
mcp.tool()(create_mock_hr_ticket)
mcp.tool()(draft_hr_email)


if __name__ == "__main__":
    # Streamable HTTP transport keeps this deployable the same way as
    # http_server.py (a plain HTTP service on $PORT); stdio is also
    # supported by FastMCP (`mcp.run(transport="stdio")`) for local,
    # process-per-client usage.
    import os

    mcp.run(transport="streamable-http", port=int(os.environ.get("PORT", "8001")))
