"""Minimal OpenRouter chat client for bot players (same setup as eventmat's AI import)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx2

from games_platform.core.auth import public_base_url

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
LLM_TIMEOUT = httpx2.Timeout(20.0, connect=5.0)


class LlmError(RuntimeError):
    pass


def llm_configured() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


async def chat(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 64,
    timeout: httpx2.Timeout = LLM_TIMEOUT,
) -> str:
    """Send a chat completion request and return the answer text."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise LlmError("OPENROUTER_API_KEY is not set")
    model = os.environ.get("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL
    base_url = os.environ.get("OPENROUTER_BASE_URL", "").strip() or DEFAULT_BASE_URL
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        # Short answers only; thinking would make the bot slow.
        "reasoning": {"enabled": False},
        # Only route to providers that don't retain or train on prompts (privacy policy).
        "provider": {"data_collection": "deny"},
    }
    try:
        async with httpx2.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                json=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": public_base_url(),
                    "X-Title": "games.jakob-r.de",
                },
            )
    except httpx2.HTTPError as e:
        raise LlmError(f"Could not reach OpenRouter: {e!r}") from e
    try:
        payload = response.json()
    except ValueError as e:
        raise LlmError(f"OpenRouter returned HTTP {response.status_code}") from e
    if response.status_code >= 400 or "error" in payload:
        message = (payload.get("error") or {}).get("message") or f"HTTP {response.status_code}"
        raise LlmError(f"OpenRouter failed: {message}")
    choices = payload.get("choices") or []
    if not choices:
        raise LlmError("OpenRouter returned no answer")
    return str((choices[0].get("message") or {}).get("content") or "")
