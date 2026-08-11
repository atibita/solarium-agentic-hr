"""
mcp_server/run_http.py
------------------------
Standalone entrypoint for running the MCP server as its own process/service:

    python -m mcp_server.run_http

Reads PORT from the environment (Render/Railway convention) so the exact
same command works locally and on a hosted free-tier platform.
"""
import os

from .http_server import create_standalone_app

if __name__ == "__main__":
    app = create_standalone_app()
    port = int(os.environ.get("PORT", "8001"))
    app.run(host="0.0.0.0", port=port)
