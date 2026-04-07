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

    Note: reasoning/thinking models (e.g. kimi-k2.5:cloud) spend tokens on an
    internal chain-of-thought before writing content. We always request at least
    8 000 tokens so the model has room to reason AND respond. Callers may pass a
    higher value if they need a longer output.
    """
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.OLLAMA_BASE_URL:
        logger.warning("OLLAMA_BASE_URL not set — skipping LLM call")
        return None

    client, model = _get_client()

    # Reasoning models need a generous token budget; enforce a safe minimum.
    effective_max_tokens = max(max_tokens, 8000)

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=effective_max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            logger.error(
                "Ollama returned empty content (finish_reason=%s). "
                "Model may need more tokens for reasoning.",
                response.choices[0].finish_reason,
            )
            return None
        return content
    except Exception as exc:
        logger.error("Ollama LLM call failed: %s", exc)
        return None
