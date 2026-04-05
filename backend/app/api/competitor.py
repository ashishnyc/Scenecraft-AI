"""Competitor insights endpoints."""
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.competitor_video import CompetitorVideo
from app.models.workspace import Workspace
from app.schemas.competitor import ChannelInsight, CompetitorInsightsResponse
from app.services.youtube_scraper import scrape_workspace

router = APIRouter(tags=["competitor"])


@router.get(
    "/workspaces/{workspace_id}/competitor-insights",
    response_model=CompetitorInsightsResponse,
)
async def get_competitor_insights(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    channel_ids: list[str] = workspace.competitor_channels or []

    # Aggregate per channel
    channels: list[ChannelInsight] = []
    for channel_id in channel_ids:
        result = await db.execute(
            select(
                func.count(CompetitorVideo.id).label("video_count"),
                func.avg(CompetitorVideo.view_count).label("avg_views"),
                func.avg(CompetitorVideo.like_count).label("avg_likes"),
                func.avg(CompetitorVideo.comment_count).label("avg_comments"),
                func.max(CompetitorVideo.scraped_at).label("last_scraped"),
            ).where(
                CompetitorVideo.workspace_id == workspace_id,
                CompetitorVideo.channel_id == channel_id,
            )
        )
        row = result.one()

        # Top 5 videos by views
        top_result = await db.execute(
            select(CompetitorVideo)
            .where(
                CompetitorVideo.workspace_id == workspace_id,
                CompetitorVideo.channel_id == channel_id,
            )
            .order_by(CompetitorVideo.view_count.desc().nulls_last())
            .limit(5)
        )
        top_videos = top_result.scalars().all()

        channels.append(ChannelInsight(
            channel_id=channel_id,
            video_count=row.video_count or 0,
            avg_views=float(row.avg_views) if row.avg_views else None,
            avg_likes=float(row.avg_likes) if row.avg_likes else None,
            avg_comments=float(row.avg_comments) if row.avg_comments else None,
            last_scraped=row.last_scraped,
            top_videos=[
                {
                    "video_id": v.video_id,
                    "title": v.title,
                    "view_count": v.view_count,
                    "like_count": v.like_count,
                    "published_at": v.published_at.isoformat() if v.published_at else None,
                }
                for v in top_videos
            ],
        ))

    return CompetitorInsightsResponse(workspace_id=workspace_id, channels=channels)


@router.post(
    "/workspaces/{workspace_id}/competitor-insights/refresh",
    status_code=status.HTTP_202_ACCEPTED,
)
async def refresh_competitor_insights(
    workspace_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    """Trigger a manual scrape of all competitor channels for this workspace."""
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    channel_ids: list[str] = workspace.competitor_channels or []
    if not channel_ids:
        return {"message": "No competitor channels configured"}

    background_tasks.add_task(
        scrape_workspace,
        str(workspace_id),
        channel_ids,
        db,
    )
    return {"message": f"Scraping {len(channel_ids)} channel(s) in background"}
