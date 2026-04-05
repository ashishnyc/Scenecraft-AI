"""APScheduler background jobs."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


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
        trigger=CronTrigger(hour=3, minute=0),  # 03:00 UTC daily
        id="daily_competitor_scrape",
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
