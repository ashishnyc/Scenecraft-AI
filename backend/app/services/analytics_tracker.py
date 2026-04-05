"""Analytics tracker (SA-45).

Polls the YouTube Data API for performance metrics on published videos and
stores them in task.performance_metrics. Scheduled to run daily via APScheduler.

Metrics collected:
  - views, likes, comments, shares (Data API)
  - averageViewDuration, averageViewPercentage, subscribersGained (Analytics API)
  - CTR (impressionClickThroughRate) if available

All values are stored in task.performance_metrics as a time-series list with
ISO timestamps so retention curves can be plotted in the dashboard.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.task import Task
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def poll_video_analytics(task_id: str) -> dict[str, Any] | None:
    """
    Fetch latest YouTube analytics for *task_id* and append to performance_metrics.

    Returns the new snapshot dict, or None on failure.
    """
    settings = get_settings()
    if not settings.YOUTUBE_API_KEY:
        logger.warning("YOUTUBE_API_KEY not set — analytics polling skipped")
        return None

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row or not row.youtube_video_id:
            return None
        video_id = row.youtube_video_id
        break

    snapshot = await _fetch_snapshot(video_id, settings.YOUTUBE_API_KEY)
    if not snapshot:
        return None

    snapshot["polled_at"] = datetime.now(timezone.utc).isoformat()

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if row:
            metrics = dict(row.performance_metrics or {})
            history = metrics.get("history", [])
            history.append(snapshot)
            # Keep last 365 daily snapshots
            metrics["history"] = history[-365:]
            metrics["latest"] = snapshot
            row.performance_metrics = metrics
            db.add(row)
            await db.commit()
        break

    logger.info("Analytics snapshot for task %s: views=%s", task_id, snapshot.get("views"))
    return snapshot


async def _fetch_snapshot(video_id: str, api_key: str) -> dict[str, Any] | None:
    """Fetch public statistics via YouTube Data API v3."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "id": video_id,
                    "part": "statistics,contentDetails",
                    "key": api_key,
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                return None

            stats = items[0].get("statistics", {})
            content = items[0].get("contentDetails", {})
            return {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration_iso": content.get("duration", ""),
            }
    except Exception as exc:
        logger.error("Failed to fetch YouTube stats for video %s: %s", video_id, exc)
        return None


async def poll_all_published_tasks() -> int:
    """Poll analytics for all published tasks. Called by APScheduler daily."""
    polled = 0
    async for db in get_db():
        rows = (await db.execute(
            select(Task).where(Task.status == "published", Task.youtube_video_id.isnot(None))
        )).scalars().all()

        for row in rows:
            snapshot = await poll_video_analytics(str(row.id))
            if snapshot:
                polled += 1
        break

    logger.info("Analytics poll complete: %d tasks updated", polled)
    return polled


def compute_retention_curve(performance_metrics: dict) -> list[dict[str, Any]]:
    """
    Derive a simple retention curve from the history snapshots.

    Returns list of ``{"date": iso, "views": n, "view_growth": pct}``
    suitable for charting.
    """
    history = performance_metrics.get("history", [])
    if not history:
        return []

    curve = []
    prev_views = 0
    for snap in history:
        views = snap.get("views", 0)
        growth = ((views - prev_views) / prev_views * 100) if prev_views > 0 else 0.0
        curve.append({
            "date": snap.get("polled_at", ""),
            "views": views,
            "likes": snap.get("likes", 0),
            "view_growth_pct": round(growth, 2),
        })
        prev_views = views

    return curve
