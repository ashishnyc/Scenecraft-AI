"""APScheduler background jobs."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def _daily_trend_refresh() -> None:
    """Refresh trending topics for every workspace."""
    from sqlalchemy import select
    from app.db.postgres import AsyncSessionLocal
    from app.models.workspace import Workspace
    from app.services.trend_refresh import refresh_trends_for_workspace
    from app.api.trends import _keywords_and_subreddits

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Workspace))
        workspaces = result.scalars().all()

    for ws in workspaces:
        keywords, subreddits = _keywords_and_subreddits(ws)
        try:
            async with AsyncSessionLocal() as db:
                saved = await refresh_trends_for_workspace(str(ws.id), keywords, subreddits, db)
            logger.info("Refreshed %d trends for workspace %s", saved, ws.id)
        except Exception as exc:
            logger.error("Trend refresh failed for workspace %s: %s", ws.id, exc)


async def _daily_pitch_generation() -> None:
    """Generate 3 pitches per workspace daily."""
    from sqlalchemy import select
    from app.db.postgres import AsyncSessionLocal
    from app.models.workspace import Workspace
    from app.models.trending_topic import TrendingTopic
    from app.models.competitor_video import CompetitorVideo
    from app.services.pitch_generator import generate_pitches

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Workspace))
        workspaces = result.scalars().all()

    for ws in workspaces:
        try:
            async with AsyncSessionLocal() as db:
                from app.api.pitches import _build_context
                topics, videos = await _build_context(ws.id, db)
                saved = await generate_pitches(
                    str(ws.id), ws.name, ws.style_guide or {},
                    topics, videos, db, count=3,
                )
            logger.info("Generated %d pitches for workspace %s", len(saved), ws.id)
        except Exception as exc:
            logger.error("Pitch generation failed for workspace %s: %s", ws.id, exc)


async def _daily_competitor_scrape() -> None:
    """Scrape competitor channels for every workspace that has them configured."""
    from sqlalchemy import select
    from app.db.postgres import AsyncSessionLocal
    from app.models.workspace import Workspace
    from app.services.youtube_scraper import scrape_workspace

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workspace).where(Workspace.competitor_channels.isnot(None))
        )
        workspaces = result.scalars().all()

    for ws in workspaces:
        channels = ws.competitor_channels or []
        if not channels:
            continue
        try:
            async with AsyncSessionLocal() as db:
                saved = await scrape_workspace(str(ws.id), channels, db)
            logger.info("Scraped %d videos for workspace %s", saved, ws.id)
        except Exception as exc:
            logger.error("Competitor scrape failed for workspace %s: %s", ws.id, exc)


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _daily_competitor_scrape,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_competitor_scrape",
        replace_existing=True,
    )
    _scheduler.add_job(
        _daily_trend_refresh,
        trigger=CronTrigger(hour=4, minute=0),
        id="daily_trend_refresh",
        replace_existing=True,
    )
    _scheduler.add_job(
        _daily_pitch_generation,
        trigger=CronTrigger(hour=5, minute=0),
        id="daily_pitch_generation",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started — daily competitor scrape at 03:00 UTC")
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
