"""YouTube Data API v3 scraper for competitor channel analysis."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
MAX_RESULTS = 50  # max allowed by YouTube API per page


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    settings = get_settings()
    params["key"] = settings.YOUTUBE_API_KEY
    resp = await client.get(f"{YOUTUBE_API_BASE}{path}", params=params)
    resp.raise_for_status()
    return resp.json()


async def fetch_channel_videos(channel_id: str) -> list[dict[str, Any]]:
    """
    Fetch up to MAX_RESULTS recent videos for a YouTube channel.
    Returns a list of dicts ready to be stored as CompetitorVideo rows.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Get uploads playlist ID for the channel
        channel_data = await _get(client, "/channels", {
            "part": "contentDetails",
            "id": channel_id,
        })
        items = channel_data.get("items", [])
        if not items:
            logger.warning("Channel not found: %s", channel_id)
            return []

        uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # 2. Fetch playlist items (video IDs)
        playlist_data = await _get(client, "/playlistItems", {
            "part": "contentDetails",
            "playlistId": uploads_playlist,
            "maxResults": MAX_RESULTS,
        })
        video_ids = [
            item["contentDetails"]["videoId"]
            for item in playlist_data.get("items", [])
        ]
        if not video_ids:
            return []

        # 3. Fetch video statistics and snippets in one call
        stats_data = await _get(client, "/videos", {
            "part": "snippet,statistics",
            "id": ",".join(video_ids),
        })

        results = []
        for item in stats_data.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})

            published_raw = snippet.get("publishedAt")
            published_at: datetime | None = None
            if published_raw:
                try:
                    published_at = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                except ValueError:
                    pass

            results.append({
                "video_id": item["id"],
                "channel_id": channel_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description"),
                "tags": snippet.get("tags"),
                "view_count": int(stats["viewCount"]) if stats.get("viewCount") else None,
                "like_count": int(stats["likeCount"]) if stats.get("likeCount") else None,
                "comment_count": int(stats["commentCount"]) if stats.get("commentCount") else None,
                "published_at": published_at,
            })

        return results


async def scrape_workspace(workspace_id: str, channel_ids: list[str], db) -> int:
    """
    Scrape all competitor channels for a workspace.
    Upserts rows into competitor_videos. Returns count of rows saved.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.competitor_video import CompetitorVideo

    total = 0
    for channel_id in channel_ids:
        try:
            videos = await fetch_channel_videos(channel_id)
        except Exception as exc:
            logger.error("Failed to scrape channel %s: %s", channel_id, exc)
            continue

        for v in videos:
            stmt = pg_insert(CompetitorVideo).values(
                id=uuid.uuid4(),
                workspace_id=uuid.UUID(workspace_id),
                scraped_at=datetime.now(tz=timezone.utc),
                **v,
            ).on_conflict_do_update(
                constraint="uq_competitor_videos_workspace_video",
                set_={
                    "title": v["title"],
                    "description": v["description"],
                    "tags": v["tags"],
                    "view_count": v["view_count"],
                    "like_count": v["like_count"],
                    "comment_count": v["comment_count"],
                    "published_at": v["published_at"],
                    "scraped_at": datetime.now(tz=timezone.utc),
                },
            )
            await db.execute(stmt)
            total += 1

        await db.commit()

    return total
