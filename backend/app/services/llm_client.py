"""Central LLM client — wraps Ollama via its OpenAI-compatible API.

Usage:
    from app.services.llm_client import llm_chat

    text = await llm_chat(
        system="You are a screenwriter.",
        user="Write a 3-act outline for ...",
        max_tokens=4096,
    )

Returns None (and logs a warning) when OLLAMA_BASE_URL is not set or the call fails.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _get_client():
    """Return a synchronous OpenAI client pointed at Ollama."""
    from openai import OpenAI
    from app.core.config import get_settings
    settings = get_settings()
    return OpenAI(
        base_url=settings.OLLAMA_BASE_URL.rstrip("/") + "/v1",
        api_key="ollama",          # Ollama ignores the key but the SDK requires it
    ), settings.OLLAMA_MODEL


def llm_chat(
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str | None:
    """
    Synchronous LLM call via Ollama.
    Returns the response text, or None on failure / missing config.
    """
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.OLLAMA_BASE_URL:
        logger.warning("OLLAMA_BASE_URL not set — skipping LLM call")
        return None

    client, model = _get_client()

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.error("Ollama LLM call failed: %s", exc)
        return None
