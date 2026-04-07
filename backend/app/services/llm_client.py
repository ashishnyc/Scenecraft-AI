"""Central LLM client — supports Ollama, OpenAI, and Anthropic.

Usage:
    from app.services.llm_client import llm_chat, resolve_ai_config

    cfg = await resolve_ai_config(workspace_id, "outline_generation", db)
    text = await llm_chat(system="...", user="...", config=cfg)

When config is None the client falls back to the global OLLAMA_BASE_URL /
OLLAMA_MODEL settings from .env (backwards-compatible).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Feature keys ────────────────────────────────────────────────────────────
# These must match the keys stored in WorkspaceAIConfig.feature_overrides.
FEATURES = [
    "project_suggestions",
    "pitch_generation",
    "outline_generation",
    "scene_planning",
    "scene_expansion",
    "consistency_check",
    "copyright_scan",
    "story_bible",
    "editorial_memory",
    "metadata_generation",
    "instagram_content",
    "instagram_replies",
]

FEATURE_LABELS = {
    "project_suggestions":  "Project / Series Suggestions",
    "pitch_generation":     "Pitch Generation",
    "outline_generation":   "Script Outline",
    "scene_planning":       "Scene Planning",
    "scene_expansion":      "Scene Expansion (Full Script)",
    "consistency_check":    "Consistency Checker",
    "copyright_scan":       "Copyright Scanner",
    "story_bible":          "Story Bible Extraction",
    "editorial_memory":     "Editorial Memory",
    "metadata_generation":  "YouTube Metadata",
    "instagram_content":    "Instagram Content",
    "instagram_replies":    "Instagram Replies",
}


@dataclass
class AIConfig:
    provider: str          # "ollama" | "openai" | "anthropic"
    model: str
    base_url: str | None   # required for ollama, ignored for openai/anthropic
    api_key: str | None    # plaintext (decrypted before use)


def _global_config() -> AIConfig:
    """Fall back to .env settings when no workspace config exists."""
    from app.core.config import get_settings
    s = get_settings()
    return AIConfig(
        provider="ollama",
        model=s.OLLAMA_MODEL,
        base_url=s.OLLAMA_BASE_URL,
        api_key=None,
    )


async def resolve_ai_config(
    workspace_id,
    feature: str,
    db,
) -> AIConfig:
    """
    Resolve the AIConfig to use for a given workspace + feature.

    Priority: feature override (named config) > workspace default config > global .env
    Returns a fully-populated AIConfig with a decrypted API key.
    """
    from app.core.encryption import decrypt
    import uuid

    try:
        from sqlalchemy import select
        from app.models.workspace_ai_config import WorkspaceAIConfig
        from app.models.workspace_ai_model_config import WorkspaceAIModelConfig

        ws_id = uuid.UUID(str(workspace_id))
        result = await db.execute(
            select(WorkspaceAIConfig).where(WorkspaceAIConfig.workspace_id == ws_id)
        )
        cfg_row = result.scalar_one_or_none()
    except Exception as exc:
        logger.warning("Could not load workspace AI config: %s", exc)
        return _global_config()

    if cfg_row is None:
        return _global_config()

    # Determine which named config to use
    named_config_id: uuid.UUID | None = None

    feature_override_id = (cfg_row.feature_overrides or {}).get(feature)
    if feature_override_id:
        try:
            named_config_id = uuid.UUID(str(feature_override_id))
        except ValueError:
            pass

    if named_config_id is None:
        named_config_id = cfg_row.default_config_id

    if named_config_id is None:
        return _global_config()

    # Load the named config
    try:
        mc_result = await db.execute(
            select(WorkspaceAIModelConfig).where(WorkspaceAIModelConfig.id == named_config_id)
        )
        mc = mc_result.scalar_one_or_none()
    except Exception as exc:
        logger.warning("Could not load named AI model config %s: %s", named_config_id, exc)
        return _global_config()

    if mc is None:
        return _global_config()

    api_key: str | None = None
    if mc.api_key_encrypted:
        try:
            api_key = decrypt(mc.api_key_encrypted)
        except Exception:
            logger.warning("Failed to decrypt API key for config %s", named_config_id)

    return AIConfig(provider=mc.provider, model=mc.model, base_url=mc.base_url, api_key=api_key)


def llm_chat(
    system: str,
    user: str,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    config: AIConfig | None = None,
) -> str | None:
    """
    Synchronous LLM call.  Supports Ollama, OpenAI, and Anthropic.
    Falls back to global .env settings when config is None.

    Reasoning models need a generous token budget; we enforce 8 000 minimum.
    """
    cfg = config or _global_config()

    effective_max_tokens = max(max_tokens, 8000)

    try:
        if cfg.provider == "anthropic":
            return _call_anthropic(cfg, system, user, effective_max_tokens, temperature)
        else:
            # OpenAI SDK works for both "openai" and "ollama" providers
            return _call_openai_compat(cfg, system, user, effective_max_tokens, temperature)
    except Exception as exc:
        logger.error("LLM call failed (provider=%s model=%s): %s", cfg.provider, cfg.model, exc)
        return None


def _call_openai_compat(
    cfg: AIConfig,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
) -> str | None:
    from openai import OpenAI

    if cfg.provider == "ollama":
        if not cfg.base_url:
            logger.warning("Ollama base_url not set — skipping LLM call")
            return None
        base_url = cfg.base_url.rstrip("/") + "/v1"
        api_key  = "ollama"
    else:
        # openai
        if not cfg.api_key:
            logger.warning("OpenAI api_key not set — skipping LLM call")
            return None
        base_url = cfg.base_url or None  # None = default OpenAI endpoint
        api_key  = cfg.api_key

    client = OpenAI(base_url=base_url, api_key=api_key)
    response = client.chat.completions.create(
        model=cfg.model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        logger.error(
            "LLM returned empty content (finish_reason=%s).",
            response.choices[0].finish_reason,
        )
        return None
    return content


def _call_anthropic(
    cfg: AIConfig,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
) -> str | None:
    import anthropic

    if not cfg.api_key:
        logger.warning("Anthropic api_key not set — skipping LLM call")
        return None

    client = anthropic.Anthropic(api_key=cfg.api_key)
    message = client.messages.create(
        model=cfg.model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text if message.content else None
