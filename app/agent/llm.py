"""
app/agent/llm.py
------------------
Thin LLM client wrapper with two backends:

  1. "openai_compatible" -- calls any OpenAI Chat Completions-compatible
     endpoint (OpenAI, Groq, OpenRouter, a local Ollama server, etc.) using
     only the standard library (`urllib`), so no extra HTTP dependency is
     required. Configured entirely via environment variables (see
     .env.example) -- no keys are ever hard-coded.

  2. "offline" -- a deterministic, template-based responder used when no
     LLM_API_KEY is configured (e.g. in CI, or a grader running purely
     locally with no API budget). It still produces a grounded, cited
     answer -- it just composes it from the retrieved chunks with a fixed
     template instead of an LLM rewrite. This keeps the whole system
     runnable and testable with zero API cost, while still demonstrating
     the full RAG + agent + MCP pipeline end-to-end.

The orchestrator only depends on `LLMClient.complete(system, user) -> str`,
so swapping providers or upgrading to a different model never touches
agent/orchestrator.py.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class LLMClient:
    def __init__(self):
        self.api_key = os.environ.get("LLM_API_KEY", "").strip()
        self.base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        self.timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "20"))
        self.enabled = bool(self.api_key)

    def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 700) -> str:
        """Return the model's text completion, or raise LLMError."""
        if not self.enabled:
            raise LLMDisabledError("No LLM_API_KEY configured; caller should use the offline fallback.")

        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }).encode("utf-8")

        req = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload["choices"][0]["message"]["content"].strip()
        except urllib.error.URLError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {exc}") from exc


class LLMError(Exception):
    pass


class LLMDisabledError(LLMError):
    pass
