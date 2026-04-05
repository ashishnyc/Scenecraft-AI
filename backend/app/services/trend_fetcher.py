"""Fetch trending signals from Google Trends, Reddit, and NewsAPI."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


async def fetch_google_trends(keywords: list[str]) -> list[dict[str, Any]]:
    """
    Returns a list of {topic, interest_value, age_hours} dicts.
    interest_value is 0-100 (pytrends scale).
    """
    if not keywords:
        return []
    try:
        from pytrends.request import TrendReq
        import asyncio

        def _sync_fetch():
            pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
            pt.build_payload(keywords[:5], timeframe="now 1-d")
            df = pt.interest_over_time()
            if df.empty:
                return []
            results = []
            for kw in keywords[:5]:
                if kw in df.columns:
                    val = int(df[kw].iloc[-1])
                    results.append({"topic": kw, "interest_value": val, "age_hours": 0})
            return results

        return await asyncio.get_event_loop().run_in_executor(None, _sync_fetch)
    except Exception as exc:
        logger.warning("Google Trends fetch failed: %s", exc)
        return []


async def fetch_reddit_posts(subreddits: list[str], limit: int = 20) -> list[dict[str, Any]]:
    """Returns a list of {topic, score, num_comments, age_hours} dicts."""
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.REDDIT_CLIENT_ID:
        logger.info("REDDIT_CLIENT_ID not configured — skipping Reddit")
        return []

    try:
        import praw
        import asyncio
        from datetime import datetime, timezone

        def _sync_fetch():
            reddit = praw.Reddit(
                client_id=settings.REDDIT_CLIENT_ID,
                client_secret=settings.REDDIT_CLIENT_SECRET,
                user_agent="ScenecraftAI/1.0",
                read_only=True,
            )
            results = []
            for sub in subreddits:
                try:
                    for post in reddit.subreddit(sub).hot(limit=limit):
                        age_hours = (
                            datetime.now(tz=timezone.utc).timestamp() - post.created_utc
                        ) / 3600
                        results.append({
                            "topic": post.title,
                            "score": post.score,
                            "num_comments": post.num_comments,
                            "age_hours": age_hours,
                            "subreddit": sub,
                        })
                except Exception as e:
                    logger.warning("Reddit subreddit %s failed: %s", sub, e)
            return results

        return await asyncio.get_event_loop().run_in_executor(None, _sync_fetch)
    except Exception as exc:
        logger.warning("Reddit fetch failed: %s", exc)
        return []


async def fetch_news_headlines(query: str) -> list[dict[str, Any]]:
    """Returns a list of {topic, relevance, age_hours} dicts."""
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.NEWS_API_KEY:
        logger.info("NEWS_API_KEY not configured — skipping NewsAPI")
        return []

    try:
        from newsapi import NewsApiClient
        import asyncio
        from datetime import datetime, timezone

        def _sync_fetch():
            client = NewsApiClient(api_key=settings.NEWS_API_KEY)
            resp = client.get_everything(q=query, language="en", sort_by="publishedAt", page_size=20)
            results = []
            for article in resp.get("articles", []):
                pub = article.get("publishedAt", "")
                age_hours = 0.0
                if pub:
                    try:
                        dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                        age_hours = (datetime.now(tz=timezone.utc) - dt).total_seconds() / 3600
                    except ValueError:
                        pass
                results.append({
                    "topic": article.get("title", ""),
                    "relevance": 1.0,
                    "age_hours": age_hours,
                    "url": article.get("url"),
                })
            return results

        return await asyncio.get_event_loop().run_in_executor(None, _sync_fetch)
    except Exception as exc:
        logger.warning("NewsAPI fetch failed: %s", exc)
        return []
