"""Pitch generation and retrieval endpoints."""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.competitor_video import CompetitorVideo
from app.models.pitch import Pitch
from app.models.project import Project
from app.models.task import Task
from app.models.trending_topic import TrendingTopic
from app.models.workspace import Workspace
from app.schemas.pitch import PitchListResponse, PitchResponse
from app.schemas.task import TaskResponse
from app.services.pitch_generator import generate_pitches

router = APIRouter(tags=["pitches"])


class PitchNotesUpdate(BaseModel):
    notes: str | None = None


class PitchApproveRequest(BaseModel):
    project_id: uuid.UUID | None = None  # defaults to first active project


async def _build_context(workspace_id: uuid.UUID, db: AsyncSession) -> tuple[list[dict], list[dict]]:
    """Fetch top trending topics and competitor videos for the workspace."""
    topics_result = await db.execute(
        select(TrendingTopic)
        .where(TrendingTopic.workspace_id == workspace_id)
        .order_by(TrendingTopic.score.desc())
        .limit(10)
    )
    topics = [
        {"topic": t.topic, "score": t.score, "source": t.source}
        for t in topics_result.scalars().all()
    ]

    videos_result = await db.execute(
        select(CompetitorVideo)
        .where(CompetitorVideo.workspace_id == workspace_id)
        .order_by(CompetitorVideo.view_count.desc().nulls_last())
        .limit(5)
    )
    videos = [
        {"title": v.title, "view_count": v.view_count or 0}
        for v in videos_result.scalars().all()
    ]

    return topics, videos


@router.get("/workspaces/{workspace_id}/pitches", response_model=PitchListResponse)
async def list_pitches(
    workspace_id: uuid.UUID,
    limit: int = 20,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    query = (
        select(Pitch)
        .where(Pitch.workspace_id == workspace_id)
        .order_by(Pitch.created_at.desc())
        .limit(limit)
    )
    if status:
        query = query.where(Pitch.status == status)

    result = await db.execute(query)
    pitches = result.scalars().all()
    return PitchListResponse(workspace_id=workspace_id, pitches=pitches)


@router.post(
    "/workspaces/{workspace_id}/pitches/generate",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_pitch_generation(
    workspace_id: uuid.UUID,
    count: int = 3,
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    topics, videos = await _build_context(workspace_id, db)

    background_tasks.add_task(
        generate_pitches,
        str(workspace_id),
        workspace.name,
        workspace.style_guide or {},
        topics,
        videos,
        db,
        count,
    )
    return {"message": f"Generating {count} pitch(es) in background"}


@router.patch(
    "/workspaces/{workspace_id}/pitches/{pitch_id}/notes",
    response_model=PitchResponse,
)
async def update_pitch_notes(
    workspace_id: uuid.UUID,
    pitch_id: uuid.UUID,
    body: PitchNotesUpdate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    pitch = await db.get(Pitch, pitch_id)
    if pitch is None or pitch.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Pitch not found")
    pitch.notes = body.notes
    await db.commit()
    await db.refresh(pitch)
    return pitch


@router.post(
    "/workspaces/{workspace_id}/pitches/{pitch_id}/approve",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def approve_pitch(
    workspace_id: uuid.UUID,
    pitch_id: uuid.UUID,
    body: PitchApproveRequest,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    """Approve a pitch: mark it approved and create an idea-state Task."""
    pitch = await db.get(Pitch, pitch_id)
    if pitch is None or pitch.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Pitch not found")

    # Resolve target project
    if body.project_id:
        project = await db.get(Project, body.project_id)
        if project is None or project.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Project not found")
    else:
        result = await db.execute(
            select(Project)
            .where(Project.workspace_id == workspace_id)
            .order_by(Project.id)
            .limit(1)
        )
        project = result.scalars().first()
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No project found in this workspace. Create a project first.",
            )

    # Create task in idea state
    task = Task(
        id=uuid.uuid4(),
        project_id=project.id,
        title=pitch.title,
        concept_brief=pitch.concept_summary,
    )
    db.add(task)

    # Mark pitch as approved
    pitch.status = "approved"
    await db.commit()
    await db.refresh(task)
    return task


@router.post(
    "/workspaces/{workspace_id}/pitches/{pitch_id}/reject",
    response_model=PitchResponse,
)
async def reject_pitch(
    workspace_id: uuid.UUID,
    pitch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    pitch = await db.get(Pitch, pitch_id)
    if pitch is None or pitch.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Pitch not found")
    pitch.status = "rejected"
    await db.commit()
    await db.refresh(pitch)
    return pitch


@router.delete(
    "/workspaces/{workspace_id}/pitches/{pitch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_pitch(
    workspace_id: uuid.UUID,
    pitch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    pitch = await db.get(Pitch, pitch_id)
    if pitch is None or pitch.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Pitch not found")
    await db.delete(pitch)
    await db.commit()
