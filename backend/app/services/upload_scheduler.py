"""Upload scheduler (SA-44).

Determines the optimal posting time for a YouTube video based on channel
analytics (best days/times for audience engagement) and triggers the upload
at the scheduled time.

Two modes:
  1. Immediate — uploads right away (privacy_status=public)
  2. Scheduled — sets privacyStatus=private with publishAt in YouTube's API,
     letting YouTube itself publish at the requested time (avoids keeping a
     long-running timer server-side).

Integration:
  - Called from tasks.py when a task transitions to `scheduled`
  - If task.script["youtube_metadata"]["scheduled_at"] is set, uses that time
  - Otherwise, calls `suggest_best_publish_time()` to find the optimal slot
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

# Best-effort defaults when no analytics data is available
# (Tuesday–Thursday 14:00–16:00 UTC tends to perform well for US audiences)
_DEFAULT_BEST_DAYS = [1, 2, 3]  # Mon=0 … Sun=6
_DEFAULT_BEST_HOUR = 15  # 3 PM UTC


async def suggest_best_publish_time(task_id: str) -> datetime:
    """
    Return a suggested publish datetime for the task.

    Uses YouTube Analytics API if YOUTUBE_API_KEY is set and channel data
    is available; falls back to a hard-coded heuristic otherwise.
    """
    settings = get_settings()

    # Try to get channel analytics
    if settings.YOUTUBE_API_KEY:
        try:
            best_time = await _fetch_channel_best_time(settings.YOUTUBE_API_KEY)
            if best_time:
                return best_time
        except Exception as exc:
            logger.warning("Could not fetch channel analytics: %s", exc)

    # Fallback: next occurrence of the heuristic best day/hour
    now = datetime.now(timezone.utc)
    days_ahead = 0
    for i in range(7):
        candidate = now + timedelta(days=i)
        if candidate.weekday() in _DEFAULT_BEST_DAYS:
            days_ahead = i
            break

    suggested = (now + timedelta(days=days_ahead)).replace(
        hour=_DEFAULT_BEST_HOUR, minute=0, second=0, microsecond=0
    )
    # If that time is in the past (same day, already passed), move to next week
    if suggested <= now:
        suggested += timedelta(weeks=1)

    logger.info("Suggested publish time for task %s: %s", task_id, suggested.isoformat())
    return suggested


async def _fetch_channel_best_time(api_key: str) -> datetime | None:
    """
    Query YouTube Analytics API for the hour-of-week with highest views.

    Returns the next occurrence of that hour, or None on error.
    """
    import httpx

    # YouTube Analytics requires OAuth — API key alone isn't sufficient.
    # We fall back gracefully when OAuth token isn't available.
    import os
    if not os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN"):
        return None

    # Get access token
    from app.services.youtube_uploader import _get_access_token
    from app.core.config import get_settings
    settings = get_settings()
    access_token = await _get_access_token(settings)
    if not access_token:
        return None

    # Fetch hourly traffic data (last 90 days)
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=90)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://youtubeanalytics.googleapis.com/v2/reports",
            params={
                "ids": "channel==MINE",
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "metrics": "views",
                "dimensions": "day,hour",
                "sort": "-views",
                "maxResults": 1,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        rows = resp.json().get("rows", [])

    if not rows:
        return None

    # rows[0] = [date_str, hour_int, views]
    best_hour = int(rows[0][1])
    now = datetime.now(timezone.utc)
    candidate = now.replace(hour=best_hour, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


async def schedule_upload(task_id: str) -> dict[str, Any]:
    """
    Determine publish time and configure the YouTube upload.

    Returns ``{"scheduled_at": iso_string, "mode": "immediate"|"scheduled"}``.
    """
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            return {"error": "Task not found"}

        script = row.script or {}
        yt_meta = script.get("youtube_metadata", {})
        explicit_time_str = yt_meta.get("scheduled_at")
        break

    now = datetime.now(timezone.utc)

    if explicit_time_str:
        try:
            scheduled_at = datetime.fromisoformat(explicit_time_str.replace("Z", "+00:00"))
        except ValueError:
            scheduled_at = await suggest_best_publish_time(task_id)
    else:
        scheduled_at = await suggest_best_publish_time(task_id)

    mode = "immediate" if scheduled_at <= now + timedelta(minutes=5) else "scheduled"

    # Persist the resolved scheduled_at back to task.script
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if row:
            sc = dict(row.script or {})
            sc.setdefault("youtube_metadata", {})["scheduled_at"] = scheduled_at.isoformat()
            sc["upload_schedule"] = {"scheduled_at": scheduled_at.isoformat(), "mode": mode}
            row.script = sc
            db.add(row)
            await db.commit()
        break

    logger.info("Upload scheduled for task %s: %s (%s)", task_id, scheduled_at.isoformat(), mode)
    return {"scheduled_at": scheduled_at.isoformat(), "mode": mode}
