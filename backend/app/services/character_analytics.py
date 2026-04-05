"""Character analytics tracker (SA-64).

Aggregates per-character engagement from YouTube performance data stored in
task.script["performance_metrics"] and task.script["cast"] (list of character names).

For each character we compute:
  - total_appearances: number of tasks/videos they appeared in
  - total_views: sum of YouTube view counts across those videos
  - avg_views_per_appearance
  - top_project_id: project with the highest view count for this character
  - engagement_breakdown: {project_id: views} mapping
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character, CharacterCasting
from app.models.task import Task
from app.schemas.character import CharacterAnalytics

logger = logging.getLogger(__name__)


async def compute_character_analytics(
    character_id: uuid.UUID,
    db: AsyncSession,
) -> CharacterAnalytics:
    """Compute engagement analytics for a single character."""
    character = await db.get(Character, character_id)
    if not character:
        return CharacterAnalytics(
            character_id=character_id,
            name="Unknown",
            total_appearances=0,
            total_views=0,
            avg_views_per_appearance=0.0,
            top_project_id=None,
            engagement_breakdown={},
        )

    # Find all projects this character is cast in
    castings = (await db.execute(
        select(CharacterCasting).where(CharacterCasting.character_id == character_id)
    )).scalars().all()

    project_ids = [c.project_id for c in castings]

    engagement_breakdown: dict[str, int] = {}
    total_views = 0
    total_appearances = 0

    for project_id in project_ids:
        # Get all published tasks in this project
        tasks = (await db.execute(
            select(Task).where(
                Task.project_id == project_id,
                Task.youtube_video_id.isnot(None),
            )
        )).scalars().all()

        project_views = 0
        for task in tasks:
            script = task.script or {}
            cast_names = script.get("cast", [])
            if character.name not in cast_names:
                continue

            metrics = script.get("performance_metrics", {})
            views = _extract_views(metrics)
            project_views += views
            total_appearances += 1

        if project_views > 0:
            engagement_breakdown[str(project_id)] = project_views
            total_views += project_views

    # Also check tasks where character name appears in script cast list directly
    # (for tasks not formally cast via CharacterCasting)
    all_tasks = (await db.execute(
        select(Task).where(
            Task.youtube_video_id.isnot(None),
        )
    )).scalars().all()

    for task in all_tasks:
        script = task.script or {}
        cast_names = script.get("cast", [])
        if character.name not in cast_names:
            continue
        if str(task.project_id) in engagement_breakdown:
            continue  # already counted

        metrics = script.get("performance_metrics", {})
        views = _extract_views(metrics)
        if views > 0:
            engagement_breakdown[str(task.project_id)] = engagement_breakdown.get(str(task.project_id), 0) + views
            total_views += views
            total_appearances += 1

    # Also use stored engagement_stats on character if available (from daily poller)
    stored = character.engagement_stats or {}
    if stored.get("total_views", 0) > total_views:
        total_views = stored["total_views"]
        total_appearances = max(total_appearances, stored.get("appearances_count", total_appearances))

    avg = total_views / total_appearances if total_appearances > 0 else 0.0
    top_project_id = max(engagement_breakdown, key=engagement_breakdown.get) if engagement_breakdown else None

    return CharacterAnalytics(
        character_id=character_id,
        name=character.name,
        total_appearances=total_appearances,
        total_views=total_views,
        avg_views_per_appearance=round(avg, 2),
        top_project_id=top_project_id,
        engagement_breakdown=engagement_breakdown,
    )


async def update_character_engagement_stats(character_id: uuid.UUID, db: AsyncSession) -> None:
    """Recompute and persist engagement stats to character.engagement_stats."""
    analytics = await compute_character_analytics(character_id, db)
    character = await db.get(Character, character_id)
    if not character:
        return

    character.engagement_stats = {
        "total_views": analytics.total_views,
        "appearances_count": analytics.total_appearances,
        "avg_views_per_appearance": analytics.avg_views_per_appearance,
        "top_project_id": analytics.top_project_id,
        "engagement_breakdown": analytics.engagement_breakdown,
    }
    await db.commit()
    logger.info("Updated engagement stats for character %s (%s)", character_id, character.name)


def _extract_views(metrics: dict[str, Any]) -> int:
    """Pull view count from performance_metrics dict (various shapes)."""
    if not metrics:
        return 0
    # Direct field
    if "view_count" in metrics:
        return int(metrics["view_count"])
    # Nested under 'statistics'
    stats = metrics.get("statistics", {})
    if "viewCount" in stats:
        return int(stats["viewCount"])
    # Retention curve data — use last cumulative value
    curve = metrics.get("retention_curve", [])
    if curve and isinstance(curve[-1], dict):
        return int(curve[-1].get("cumulative_views", 0))
    return 0
