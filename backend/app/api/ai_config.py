"""Workspace AI configuration API — named model configs + feature overrides."""
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
from app.models.workspace_ai_model_config import WorkspaceAIModelConfig
from app.services.llm_client import FEATURES, FEATURE_LABELS

router = APIRouter(tags=["ai-config"])

# ── Model catalog ─────────────────────────────────────────────────────────────

PROVIDER_MODELS: dict[str, list[str]] = {
    "ollama":    ["kimi-k2.5:cloud", "deepseek-coder-v2:lite", "qwen2.5-coder:32b", "llama3.1:8b", "mistral:7b"],
    "openai":    ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "anthropic": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
}

PROVIDERS = [
    {"value": "ollama",    "label": "Ollama (local)"},
    {"value": "openai",    "label": "OpenAI"},
    {"value": "anthropic", "label": "Anthropic"},
]

# ── Schemas ───────────────────────────────────────────────────────────────────

class ModelConfigCreate(BaseModel):
    name: str
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None      # plaintext — encrypted before storage
    is_default: bool = False


class ModelConfigUpdate(BaseModel):
    name: str
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None      # None = keep existing; "" = clear
    is_default: bool = False


class ModelConfigOut(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    base_url: str | None
    has_api_key: bool
    is_default: bool


class FeatureOverridesUpdate(BaseModel):
    # Maps feature key → named config ID (UUID string) or null to clear
    overrides: dict[str, str | None]


class AIConfigOut(BaseModel):
    default_config_id: str | None
    feature_overrides: dict[str, str]       # feature → config_id string
    model_configs: list[ModelConfigOut]
    features: list[dict[str, str]]          # [{key, label}]
    providers: list[dict[str, str]]         # [{value, label}]
    provider_models: dict[str, list[str]]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mc_out(mc: WorkspaceAIModelConfig) -> ModelConfigOut:
    return ModelConfigOut(
        id=str(mc.id),
        name=mc.name,
        provider=mc.provider,
        model=mc.model,
        base_url=mc.base_url,
        has_api_key=bool(mc.api_key_encrypted),
        is_default=mc.is_default,
    )


async def _get_or_create_cfg(workspace_id: uuid.UUID, db: AsyncSession) -> WorkspaceAIConfig:
    result = await db.execute(
        select(WorkspaceAIConfig).where(WorkspaceAIConfig.workspace_id == workspace_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = WorkspaceAIConfig(id=uuid.uuid4(), workspace_id=workspace_id)
        db.add(row)
        await db.flush()
    return row


async def _full_out(workspace_id: uuid.UUID, db: AsyncSession) -> AIConfigOut:
    cfg = await _get_or_create_cfg(workspace_id, db)
    mcs_result = await db.execute(
        select(WorkspaceAIModelConfig)
        .where(WorkspaceAIModelConfig.workspace_id == workspace_id)
        .order_by(WorkspaceAIModelConfig.created_at)
    )
    mcs = mcs_result.scalars().all()
    return AIConfigOut(
        default_config_id=str(cfg.default_config_id) if cfg.default_config_id else None,
        feature_overrides=cfg.feature_overrides or {},
        model_configs=[_mc_out(mc) for mc in mcs],
        features=[{"key": k, "label": FEATURE_LABELS[k]} for k in FEATURES],
        providers=PROVIDERS,
        provider_models=PROVIDER_MODELS,
    )


# ── Routes: full config ───────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/ai-config", response_model=AIConfigOut)
async def get_ai_config(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    if not await db.get(Workspace, workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    out = await _full_out(workspace_id, db)
    await db.commit()
    return out


# ── Routes: named model configs ───────────────────────────────────────────────

@router.post("/workspaces/{workspace_id}/ai-model-configs", response_model=ModelConfigOut, status_code=201)
async def create_model_config(
    workspace_id: uuid.UUID,
    body: ModelConfigCreate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    from app.core.encryption import encrypt

    if not await db.get(Workspace, workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    # If this is being set as default, unset any existing default
    if body.is_default:
        existing = (await db.execute(
            select(WorkspaceAIModelConfig)
            .where(WorkspaceAIModelConfig.workspace_id == workspace_id,
                   WorkspaceAIModelConfig.is_default == True)  # noqa: E712
        )).scalars().all()
        for mc in existing:
            mc.is_default = False

    mc = WorkspaceAIModelConfig(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name=body.name,
        provider=body.provider,
        model=body.model,
        base_url=body.base_url or None,
        api_key_encrypted=encrypt(body.api_key) if body.api_key else None,
        is_default=body.is_default,
    )
    db.add(mc)

    # Wire up as workspace default config if flagged
    if body.is_default:
        cfg = await _get_or_create_cfg(workspace_id, db)
        cfg.default_config_id = mc.id

    await db.commit()
    await db.refresh(mc)
    return _mc_out(mc)


@router.put("/workspaces/{workspace_id}/ai-model-configs/{config_id}", response_model=ModelConfigOut)
async def update_model_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    body: ModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    from app.core.encryption import encrypt

    mc = await db.get(WorkspaceAIModelConfig, config_id)
    if mc is None or mc.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Config not found")

    # Handle default switching
    if body.is_default and not mc.is_default:
        existing = (await db.execute(
            select(WorkspaceAIModelConfig)
            .where(WorkspaceAIModelConfig.workspace_id == workspace_id,
                   WorkspaceAIModelConfig.is_default == True)  # noqa: E712
        )).scalars().all()
        for other in existing:
            other.is_default = False
        cfg = await _get_or_create_cfg(workspace_id, db)
        cfg.default_config_id = mc.id
    elif not body.is_default and mc.is_default:
        # Unsetting default — clear workspace pointer too
        cfg = await _get_or_create_cfg(workspace_id, db)
        if cfg.default_config_id == mc.id:
            cfg.default_config_id = None

    mc.name = body.name
    mc.provider = body.provider
    mc.model = body.model
    mc.base_url = body.base_url or None
    mc.is_default = body.is_default

    if body.api_key:
        mc.api_key_encrypted = encrypt(body.api_key)
    elif body.api_key == "":
        mc.api_key_encrypted = None
    # None = keep existing

    await db.commit()
    await db.refresh(mc)
    return _mc_out(mc)


@router.delete("/workspaces/{workspace_id}/ai-model-configs/{config_id}", status_code=204)
async def delete_model_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    mc = await db.get(WorkspaceAIModelConfig, config_id)
    if mc is None or mc.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Config not found")

    # Block delete if it's the workspace default
    cfg = await _get_or_create_cfg(workspace_id, db)
    if cfg.default_config_id == config_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete: this config is the workspace default. Set another config as default first.",
        )

    # Block delete if used in any feature override
    overrides = cfg.feature_overrides or {}
    used_in = [f for f, cid in overrides.items() if str(cid) == str(config_id)]
    if used_in:
        labels = ", ".join(FEATURE_LABELS.get(f, f) for f in used_in)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete: config is used in feature override(s): {labels}.",
        )

    await db.delete(mc)
    await db.commit()


# ── Routes: feature overrides ─────────────────────────────────────────────────

@router.put("/workspaces/{workspace_id}/ai-config/overrides")
async def update_feature_overrides(
    workspace_id: uuid.UUID,
    body: FeatureOverridesUpdate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    if not await db.get(Workspace, workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    cfg = await _get_or_create_cfg(workspace_id, db)
    current: dict[str, Any] = dict(cfg.feature_overrides or {})

    for feature, config_id in body.overrides.items():
        if config_id is None:
            current.pop(feature, None)
        else:
            # Validate the config belongs to this workspace
            mc = await db.get(WorkspaceAIModelConfig, uuid.UUID(config_id))
            if mc is None or mc.workspace_id != workspace_id:
                raise HTTPException(status_code=400, detail=f"Invalid config ID for feature '{feature}'")
            current[feature] = config_id

    cfg.feature_overrides = current
    await db.commit()
    return await _full_out(workspace_id, db)


# ── Routes: set default ───────────────────────────────────────────────────────

@router.put("/workspaces/{workspace_id}/ai-config/default/{config_id}")
async def set_default_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    mc = await db.get(WorkspaceAIModelConfig, config_id)
    if mc is None or mc.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Config not found")

    # Unset old default
    existing = (await db.execute(
        select(WorkspaceAIModelConfig)
        .where(WorkspaceAIModelConfig.workspace_id == workspace_id,
               WorkspaceAIModelConfig.is_default == True)  # noqa: E712
    )).scalars().all()
    for other in existing:
        other.is_default = False

    mc.is_default = True
    cfg = await _get_or_create_cfg(workspace_id, db)
    cfg.default_config_id = config_id
    await db.commit()
    return await _full_out(workspace_id, db)


# ── Routes: test ──────────────────────────────────────────────────────────────

@router.post("/workspaces/{workspace_id}/ai-config/test")
async def test_ai_config(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    from app.services.llm_client import resolve_ai_config, llm_chat
    config = await resolve_ai_config(workspace_id, "project_suggestions", db)
    result = llm_chat(system="You are a helpful assistant.", user="Reply with exactly: OK", max_tokens=8000, config=config)
    if result and "OK" in result:
        return {"status": "ok", "provider": config.provider, "model": config.model}
    return {"status": "error", "detail": "Model did not respond as expected", "raw": result}
