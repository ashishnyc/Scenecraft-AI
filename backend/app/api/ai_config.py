"""Workspace AI configuration API."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.workspace import Workspace
from app.models.workspace_ai_config import WorkspaceAIConfig
from app.services.llm_client import FEATURES, FEATURE_LABELS

router = APIRouter(tags=["ai-config"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class FeatureOverride(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None          # plaintext — encrypted before storage


class AIConfigUpdate(BaseModel):
    provider: str                        # "ollama" | "openai" | "anthropic"
    model: str
    base_url: str | None = None
    api_key: str | None = None          # plaintext — encrypted before storage
    feature_overrides: dict[str, FeatureOverride] = {}


class FeatureOverrideOut(BaseModel):
    provider: str | None
    model: str | None
    base_url: str | None
    has_api_key: bool                   # never return the raw key


class AIConfigOut(BaseModel):
    provider: str
    model: str
    base_url: str | None
    has_api_key: bool
    feature_overrides: dict[str, FeatureOverrideOut]
    features: list[dict[str, str]]      # [{key, label}] for UI


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mask(cfg_row: WorkspaceAIConfig) -> AIConfigOut:
    overrides_out: dict[str, FeatureOverrideOut] = {}
    for feature, ov in (cfg_row.feature_overrides or {}).items():
        overrides_out[feature] = FeatureOverrideOut(
            provider=ov.get("provider"),
            model=ov.get("model"),
            base_url=ov.get("base_url"),
            has_api_key=bool(ov.get("api_key_encrypted")),
        )
    return AIConfigOut(
        provider=cfg_row.provider,
        model=cfg_row.model,
        base_url=cfg_row.base_url,
        has_api_key=bool(cfg_row.api_key_encrypted),
        feature_overrides=overrides_out,
        features=[{"key": k, "label": FEATURE_LABELS[k]} for k in FEATURES],
    )


async def _get_or_create(workspace_id: uuid.UUID, db: AsyncSession) -> WorkspaceAIConfig:
    result = await db.execute(
        select(WorkspaceAIConfig).where(WorkspaceAIConfig.workspace_id == workspace_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        from app.core.config import get_settings
        s = get_settings()
        row = WorkspaceAIConfig(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            provider="ollama",
            model=s.OLLAMA_MODEL,
            base_url=s.OLLAMA_BASE_URL,
        )
        db.add(row)
        await db.flush()
    return row


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/ai-config", response_model=AIConfigOut)
async def get_ai_config(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    row = await _get_or_create(workspace_id, db)
    await db.commit()
    return _mask(row)


@router.put("/workspaces/{workspace_id}/ai-config", response_model=AIConfigOut)
async def update_ai_config(
    workspace_id: uuid.UUID,
    body: AIConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    from app.core.encryption import encrypt

    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    row = await _get_or_create(workspace_id, db)

    row.provider = body.provider
    row.model = body.model
    row.base_url = body.base_url or None

    # Only update the API key if a new one was provided (non-empty string)
    if body.api_key:
        row.api_key_encrypted = encrypt(body.api_key)
    elif body.api_key == "":
        # Explicit clear
        row.api_key_encrypted = None

    # Build feature overrides — encrypt per-feature keys if provided
    overrides: dict[str, Any] = {}
    for feature, ov in body.feature_overrides.items():
        entry: dict[str, Any] = {}
        if ov.provider:
            entry["provider"] = ov.provider
        if ov.model:
            entry["model"] = ov.model
        if ov.base_url:
            entry["base_url"] = ov.base_url
        if ov.api_key:
            entry["api_key_encrypted"] = encrypt(ov.api_key)
        elif ov.api_key == "":
            entry["api_key_encrypted"] = None
        else:
            # Preserve existing encrypted key if not touched
            existing = (row.feature_overrides or {}).get(feature, {})
            if existing.get("api_key_encrypted"):
                entry["api_key_encrypted"] = existing["api_key_encrypted"]
        if entry:
            overrides[feature] = entry

    row.feature_overrides = overrides
    await db.commit()
    await db.refresh(row)
    return _mask(row)


@router.post("/workspaces/{workspace_id}/ai-config/test")
async def test_ai_config(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    """Quick connectivity test using the workspace's default AI config."""
    from app.services.llm_client import resolve_ai_config, llm_chat

    config = await resolve_ai_config(workspace_id, "project_suggestions", db)
    result = llm_chat(
        system="You are a helpful assistant.",
        user="Reply with exactly: OK",
        max_tokens=8000,
        config=config,
    )
    if result and "OK" in result:
        return {"status": "ok", "provider": config.provider, "model": config.model}
    return {"status": "error", "detail": "Model did not respond as expected", "raw": result}
