"""Feedback loop (SA-47).

After a video accumulates enough analytics data, this service scores it
against content intelligence criteria and stores the result back in Qdrant
so future pitch scoring benefits from real performance data.

Score formula:
  content_score = 0.4 * view_velocity + 0.3 * like_rate + 0.3 * retention

  where:
    view_velocity  = views_30d / channel_avg_views (capped at 2.0)
    like_rate      = likes / views (capped at 0.1 = 10 %)
    retention      = averageViewPercentage / 100 (if available, else 0.5)

The score (0–1) is stored alongside the video's embedding vector in Qdrant
collection "content_performance" so future originality/pitch checks can
penalise over-used topics AND reward high-performing patterns.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.task import Task
from sqlalchemy import select

logger = logging.getLogger(__name__)

_COLLECTION = "content_performance"


def compute_content_score(performance_metrics: dict) -> float:
    """
    Compute a normalised content score (0–1) from performance metrics.
    """
    latest = performance_metrics.get("latest", {})
    history = performance_metrics.get("history", [])

    views = latest.get("views", 0)
    likes = latest.get("likes", 0)
    retention = latest.get("average_view_percentage", 50.0)  # default 50% if missing

    # View velocity: compare 30-day growth to a baseline of 1000 views
    views_30d = 0
    if len(history) >= 2:
        views_30d = history[-1].get("views", 0) - history[-31].get("views", 0) if len(history) >= 31 else views
    else:
        views_30d = views

    channel_avg = 1000  # placeholder; ideally pulled from analytics
    view_velocity = min(views_30d / max(channel_avg, 1), 2.0) / 2.0  # normalise to 0-1

    like_rate = min(likes / max(views, 1), 0.10) / 0.10  # normalise 10% cap → 1.0

    retention_score = retention / 100.0

    score = 0.4 * view_velocity + 0.3 * like_rate + 0.3 * retention_score
    return round(min(max(score, 0.0), 1.0), 4)


async def store_performance_vector(task_id: str) -> bool:
    """
    Compute content score and upsert the task's topic embedding + score into Qdrant.

    Returns True on success.
    """
    settings = get_settings()

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row or not row.performance_metrics:
            return False

        metrics = row.performance_metrics
        script = row.script or {}
        outline = script.get("outline", {})
        title = row.title or ""
        logline = outline.get("logline", "")
        break

    score = compute_content_score(metrics)
    text_to_embed = f"{title}. {logline}"

    # Generate embedding via Claude (same approach as originality checker)
    try:
        from app.services.vector_store import embed_text, upsert_vector
        vector = await embed_text(text_to_embed)
        if vector is None:
            logger.warning("Could not generate embedding for task %s", task_id)
            return False

        payload = {
            "task_id": task_id,
            "title": title,
            "content_score": score,
            "views": metrics.get("latest", {}).get("views", 0),
        }
        await upsert_vector(_COLLECTION, task_id, vector, payload)
        logger.info("Stored performance vector for task %s (score=%.4f)", task_id, score)
        return True
    except Exception as exc:
        logger.error("Failed to store performance vector for task %s: %s", task_id, exc)
        return False


async def run_feedback_loop_for_all() -> int:
    """Process all published tasks with sufficient analytics data."""
    processed = 0
    async for db in get_db():
        rows = (await db.execute(
            select(Task).where(
                Task.status == "published",
                Task.performance_metrics.isnot(None),
            )
        )).scalars().all()

        for row in rows:
            metrics = row.performance_metrics or {}
            # Only process tasks with at least 7 days of data
            if len(metrics.get("history", [])) >= 7:
                ok = await store_performance_vector(str(row.id))
                if ok:
                    processed += 1
        break

    logger.info("Feedback loop processed %d tasks", processed)
    return processed
