"""Character library — CRUD, visual identity, casting, and analytics (SA-60–64)."""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.character import Character, CharacterCasting
from app.schemas.character import (
    CharacterCreate, CharacterResponse, CharacterUpdate,
    AppearanceVersionCreate, CastingCreate, CastingUpdate, CastingResponse,
    CharacterAnalytics,
)

router = APIRouter(tags=["characters"])


# ── SA-60: Talent Roster CRUD ─────────────────────────────────────────────────

@router.post("/characters", response_model=CharacterResponse, status_code=status.HTTP_201_CREATED)
async def create_character(
    body: CharacterCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    character = Character(
        id=uuid.uuid4(),
        account_id=uuid.UUID(user_id),
        visual_references={"images": []},
        appearance_state={"versions": []},
        engagement_stats={"total_views": 0, "appearances": []},
        **body.model_dump(),
    )
    db.add(character)
    await db.commit()
    await db.refresh(character)
    return character


@router.get("/characters", response_model=list[CharacterResponse])
async def list_characters(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(
        select(Character)
        .where(Character.account_id == uuid.UUID(user_id))
        .order_by(Character.name)
    )
    return result.scalars().all()


@router.get("/characters/{character_id}", response_model=CharacterResponse)
async def get_character(
    character_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    character = await db.get(Character, character_id)
    if character is None or character.account_id != uuid.UUID(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    return character


@router.put("/characters/{character_id}", response_model=CharacterResponse)
async def update_character(
    character_id: uuid.UUID,
    body: CharacterUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    character = await db.get(Character, character_id)
    if character is None or character.account_id != uuid.UUID(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(character, field, value)

    await db.commit()
    await db.refresh(character)
    return character


@router.delete("/characters/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_character(
    character_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    character = await db.get(Character, character_id)
    if character is None or character.account_id != uuid.UUID(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    await db.delete(character)
    await db.commit()


# ── SA-61: Visual identity ────────────────────────────────────────────────────

@router.post("/characters/{character_id}/visual-references", response_model=CharacterResponse)
async def upload_visual_reference(
    character_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Upload a reference image and store its S3 URL in visual_references.images."""
    from app.db.s3 import get_s3_client
    from app.core.config import get_settings

    character = await db.get(Character, character_id)
    if character is None or character.account_id != uuid.UUID(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    settings = get_settings()
    s3 = get_s3_client()
    ext = (file.filename or "img").rsplit(".", 1)[-1].lower()
    key = f"characters/{character_id}/refs/{uuid.uuid4()}.{ext}"
    content = await file.read()

    s3.put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=file.content_type or "application/octet-stream",
    )
    url = f"s3://{settings.S3_BUCKET}/{key}"

    refs = dict(character.visual_references or {"images": []})
    refs.setdefault("images", [])
    refs["images"].append({"url": url, "filename": file.filename, "key": key})
    character.visual_references = refs

    await db.commit()
    await db.refresh(character)
    return character


@router.post("/characters/{character_id}/appearance-versions", response_model=CharacterResponse)
async def add_appearance_version(
    character_id: uuid.UUID,
    body: AppearanceVersionCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Add a named appearance version (e.g. 'Season 2 look', 'Villain arc')."""
    character = await db.get(Character, character_id)
    if character is None or character.account_id != uuid.UUID(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    state = dict(character.appearance_state or {"versions": []})
    state.setdefault("versions", [])
    version_id = str(uuid.uuid4())
    state["versions"].append({
        "id": version_id,
        "label": body.label,
        "description": body.description,
        "image_url": body.image_url,
        "created_at": __import__("datetime").datetime.utcnow().isoformat(),
    })
    state["active_version_id"] = version_id
    character.appearance_state = state

    await db.commit()
    await db.refresh(character)
    return character


@router.put("/characters/{character_id}/lora-model", response_model=CharacterResponse)
async def set_lora_model(
    character_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Set the LoRA model URL for a character."""
    character = await db.get(Character, character_id)
    if character is None or character.account_id != uuid.UUID(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    lora_url = body.get("lora_model_url")
    if not lora_url:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="lora_model_url required")

    character.lora_model_url = lora_url
    await db.commit()
    await db.refresh(character)
    return character


# ── SA-62: Casting system ─────────────────────────────────────────────────────

@router.post("/projects/{project_id}/cast", response_model=CastingResponse, status_code=status.HTTP_201_CREATED)
async def cast_character(
    project_id: uuid.UUID,
    body: CastingCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Cast a character into a project with a role and arc notes."""
    from app.models.project import Project

    project = await db.get(Project, project_id)
    if project is None or str(project.workspace_id) not in await _user_workspace_ids(db, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    character = await db.get(Character, body.character_id)
    if character is None or character.account_id != uuid.UUID(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    # Check not already cast
    existing = (await db.execute(
        select(CharacterCasting)
        .where(CharacterCasting.project_id == project_id)
        .where(CharacterCasting.character_id == body.character_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Character already cast in this project")

    casting = CharacterCasting(
        id=uuid.uuid4(),
        project_id=project_id,
        **body.model_dump(),
    )
    db.add(casting)
    await db.commit()

    result = await db.execute(
        select(CharacterCasting)
        .where(CharacterCasting.id == casting.id)
        .options(selectinload(CharacterCasting.character))
    )
    return result.scalar_one()


@router.get("/projects/{project_id}/cast", response_model=list[CastingResponse])
async def list_cast(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """List all characters cast in a project."""
    result = await db.execute(
        select(CharacterCasting)
        .where(CharacterCasting.project_id == project_id)
        .options(selectinload(CharacterCasting.character))
        .order_by(CharacterCasting.role)
    )
    return result.scalars().all()


@router.put("/projects/{project_id}/cast/{casting_id}", response_model=CastingResponse)
async def update_casting(
    project_id: uuid.UUID,
    casting_id: uuid.UUID,
    body: CastingUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    casting = await db.get(CharacterCasting, casting_id)
    if casting is None or casting.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Casting not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(casting, field, value)

    await db.commit()

    result = await db.execute(
        select(CharacterCasting)
        .where(CharacterCasting.id == casting_id)
        .options(selectinload(CharacterCasting.character))
    )
    return result.scalar_one()


@router.delete("/projects/{project_id}/cast/{casting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_cast(
    project_id: uuid.UUID,
    casting_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    casting = await db.get(CharacterCasting, casting_id)
    if casting is None or casting.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Casting not found")
    await db.delete(casting)
    await db.commit()


# ── SA-64: Character analytics ────────────────────────────────────────────────

@router.get("/characters/{character_id}/analytics", response_model=CharacterAnalytics)
async def get_character_analytics(
    character_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Aggregate per-character engagement from YouTube performance data."""
    from app.services.character_analytics import compute_character_analytics
    character = await db.get(Character, character_id)
    if character is None or character.account_id != uuid.UUID(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    return await compute_character_analytics(character_id, db)


@router.get("/workspaces/{workspace_id}/character-analytics", response_model=list[CharacterAnalytics])
async def get_workspace_character_analytics(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Leaderboard: all characters ranked by total views for a workspace."""
    from app.services.character_analytics import compute_character_analytics

    chars = (await db.execute(
        select(Character).where(Character.account_id == uuid.UUID(user_id))
    )).scalars().all()

    results = []
    for char in chars:
        analytics = await compute_character_analytics(char.id, db)
        results.append(analytics)

    results.sort(key=lambda x: x.total_views, reverse=True)
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _user_workspace_ids(db: AsyncSession, user_id: str) -> set[str]:
    from app.models.workspace import Workspace
    rows = (await db.execute(
        select(Workspace.id).where(Workspace.owner_id == uuid.UUID(user_id))
    )).scalars().all()
    return {str(r) for r in rows}
