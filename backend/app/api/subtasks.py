"""Subtask CRUD with dependency ordering and blocking."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.subtask import Subtask, SubtaskStatus
from app.models.task import Task
from app.schemas.subtask import SubtaskCreate, SubtaskResponse, SubtaskUpdate
from app.services.dag import check_dependencies_met, topological_sort

router = APIRouter(tags=["subtasks"])


@router.post("/tasks/{task_id}/subtasks", response_model=SubtaskResponse, status_code=status.HTTP_201_CREATED)
async def create_subtask(
    task_id: uuid.UUID,
    body: SubtaskCreate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    subtask = Subtask(
        id=uuid.uuid4(),
        task_id=task_id,
        type=body.type,
        depends_on=body.depends_on or None,
    )
    db.add(subtask)
    await db.commit()
    await db.refresh(subtask)
    return subtask


@router.get("/tasks/{task_id}/subtasks", response_model=list[SubtaskResponse])
async def list_subtasks(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    result = await db.execute(select(Subtask).where(Subtask.task_id == task_id))
    subtasks = result.scalars().all()
    return topological_sort(list(subtasks))


@router.put("/subtasks/{subtask_id}", response_model=SubtaskResponse)
async def update_subtask(
    subtask_id: uuid.UUID,
    body: SubtaskUpdate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    subtask = await db.get(Subtask, subtask_id)
    if subtask is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subtask not found")

    # Block starting if dependencies are unmet
    if body.status == SubtaskStatus.running:
        result = await db.execute(select(Subtask).where(Subtask.task_id == subtask.task_id))
        all_subtasks = result.scalars().all()
        unmet = check_dependencies_met(subtask, list(all_subtasks))
        if unmet:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot start subtask: dependencies not done yet: {unmet}",
            )

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(subtask, field, value)

    await db.commit()
    await db.refresh(subtask)
    return subtask
