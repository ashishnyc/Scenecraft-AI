"""Character library CRUD endpoints."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.character import Character
from app.schemas.character import CharacterCreate, CharacterResponse, CharacterUpdate

router = APIRouter(tags=["characters"])


@router.post("/characters", response_model=CharacterResponse, status_code=status.HTTP_201_CREATED)
async def create_character(
    body: CharacterCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    character = Character(
        id=uuid.uuid4(),
        account_id=uuid.UUID(user_id),
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
