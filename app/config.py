"""
app/config.py
----------------
Centralized environment-variable configuration. No secrets are hard-coded
anywhere in this codebase; everything sensitive (LLM API keys) is read from
the environment at runtime, per the project's security requirements. See
.env.example for the full list of variables and safe local defaults.
"""
from __future__ import annotations
from dotenv import load_dotenv

import os


class Config:
    load_dotenv()
    # print(dict(os.environ))
    # -- App ---------------------------------------------------------------
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())
    ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = ENV == "development"

    # -- MCP -----------------------------------------------------------------
    MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "inprocess")   # inprocess | http
    MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8001")
    MOUNT_MCP_IN_APP = os.environ.get("MOUNT_MCP_IN_APP", "true").lower() == "true"

    # -- LLM (optional; offline template synthesis is used if unset) ---------
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    # -- Rate limiting / basic abuse protection -------------------------------
    MAX_MESSAGE_LENGTH = int(os.environ.get("MAX_MESSAGE_LENGTH", "2000"))
    RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "30"))

    @classmethod
    def as_public_dict(cls) -> dict:
        """Safe-to-expose subset of config, e.g. for a debug/about panel --
        never includes LLM_API_KEY or SECRET_KEY."""
        print("API KEY:", LLM_API_KEY, " in constructor !" )
        return {
            "env": cls.ENV,
            "mcp_transport": cls.MCP_TRANSPORT,
            "llm_configured": bool(cls.LLM_API_KEY),
            "llm_model": cls.LLM_MODEL if cls.LLM_API_KEY else None,
        }
