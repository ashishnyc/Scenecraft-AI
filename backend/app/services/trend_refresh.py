"""Orchestrate trend detection for a workspace and persist results."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trending_topic import TrendingTopic
from app.services.trend_fetcher import fetch_google_trends, fetch_reddit_posts, fetch_news_headlines
from app.services.trend_scorer import score_google_trend, score_reddit_post, score_news_article

logger = logging.getLogger(__name__)


async def refresh_trends_for_workspace(
    workspace_id: str,
    keywords: list[str],
    subreddits: list[str],
    db: AsyncSession,
) -> int:
    """
    Fetch, score, and store trending topics for a workspace.
    Old rows for this workspace are deleted before inserting new ones.
    Returns the number of rows saved.
    """
    from sqlalchemy import delete

    rows: list[TrendingTopic] = []
    query = " ".join(keywords) if keywords else "trending"

    # 1. Google Trends
    gt_signals = await fetch_google_trends(keywords)
    for sig in gt_signals:
        s = score_google_trend(sig["topic"], sig["interest_value"], sig.get("age_hours", 0))
        rows.append(TrendingTopic(
            id=uuid.uuid4(),
            workspace_id=uuid.UUID(workspace_id),
            topic=sig["topic"],
            source="google_trends",
            score=s,
            raw_data=sig,
            detected_at=datetime.now(tz=timezone.utc),
        ))

    # 2. Reddit
    reddit_signals = await fetch_reddit_posts(subreddits)
    for sig in reddit_signals:
        s = score_reddit_post(sig["topic"], sig["score"], sig["num_comments"], sig.get("age_hours", 0))
        rows.append(TrendingTopic(
            id=uuid.uuid4(),
            workspace_id=uuid.UUID(workspace_id),
            topic=sig["topic"],
            source="reddit",
            score=s,
            raw_data={k: v for k, v in sig.items() if k != "topic"},
            detected_at=datetime.now(tz=timezone.utc),
        ))

    # 3. News
    news_signals = await fetch_news_headlines(query)
    for sig in news_signals:
        s = score_news_article(sig["topic"], sig.get("relevance", 1.0), sig.get("age_hours", 0))
        rows.append(TrendingTopic(
            id=uuid.uuid4(),
            workspace_id=uuid.UUID(workspace_id),
            topic=sig["topic"],
            source="news",
            score=s,
            raw_data={k: v for k, v in sig.items() if k != "topic"},
            detected_at=datetime.now(tz=timezone.utc),
        ))

    if not rows:
        logger.info("No trend signals for workspace %s", workspace_id)
        return 0

    # Replace old rows for this workspace
    await db.execute(
        delete(TrendingTopic).where(TrendingTopic.workspace_id == uuid.UUID(workspace_id))
    )
    db.add_all(rows)
    await db.commit()
    logger.info("Saved %d trending topics for workspace %s", len(rows), workspace_id)
    return len(rows)
