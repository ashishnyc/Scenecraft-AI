"""Trending topics endpoints."""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.trending_topic import TrendingTopic
from app.models.workspace import Workspace
from app.schemas.trend import TrendingTopicResponse, TrendsResponse
from app.services.trend_refresh import refresh_trends_for_workspace

router = APIRouter(tags=["trends"])


def _keywords_and_subreddits(workspace: Workspace) -> tuple[list[str], list[str]]:
    """Extract keywords and subreddits from workspace style_guide."""
    guide = workspace.style_guide or {}
    keywords: list[str] = guide.get("keywords", [])
    subreddits: list[str] = guide.get("subreddits", [])
    # Fall back to workspace name as a keyword
    if not keywords:
        keywords = [workspace.name]
    return keywords, subreddits


@router.get("/workspaces/{workspace_id}/trends", response_model=TrendsResponse)
async def get_trends(
    workspace_id: uuid.UUID,
    limit: int = 50,
    source: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    query = (
        select(TrendingTopic)
        .where(TrendingTopic.workspace_id == workspace_id)
        .order_by(TrendingTopic.score.desc())
        .limit(limit)
    )
    if source:
        query = query.where(TrendingTopic.source == source)

    result = await db.execute(query)
    topics = result.scalars().all()

    return TrendsResponse(workspace_id=workspace_id, topics=topics)


@router.post(
    "/workspaces/{workspace_id}/trends/refresh",
    status_code=status.HTTP_202_ACCEPTED,
)
async def refresh_trends(
    workspace_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    keywords, subreddits = _keywords_and_subreddits(workspace)
    background_tasks.add_task(
        refresh_trends_for_workspace,
        str(workspace_id),
        keywords,
        subreddits,
        db,
    )
    return {"message": "Trend refresh started in background"}
