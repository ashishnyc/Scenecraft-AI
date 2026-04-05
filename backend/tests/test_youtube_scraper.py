"""Integration tests for the YouTube scraper service (YouTube API mocked)."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


MOCK_CHANNEL_RESPONSE = {
    "items": [{
        "contentDetails": {
            "relatedPlaylists": {"uploads": "UU_test_playlist"}
        }
    }]
}

MOCK_PLAYLIST_RESPONSE = {
    "items": [
        {"contentDetails": {"videoId": "vid1"}},
        {"contentDetails": {"videoId": "vid2"}},
    ]
}

MOCK_VIDEOS_RESPONSE = {
    "items": [
        {
            "id": "vid1",
            "snippet": {
                "title": "How to Build an AI App",
                "description": "Full tutorial",
                "tags": ["ai", "python"],
                "publishedAt": "2024-01-15T10:00:00Z",
            },
            "statistics": {
                "viewCount": "150000",
                "likeCount": "4200",
                "commentCount": "310",
            },
        },
        {
            "id": "vid2",
            "snippet": {
                "title": "React Tutorial for Beginners",
                "description": "Learn React",
                "tags": ["react", "javascript"],
                "publishedAt": "2024-02-01T08:00:00Z",
            },
            "statistics": {
                "viewCount": "98000",
                "likeCount": "2100",
                "commentCount": "180",
            },
        },
    ]
}


def _mock_get_factory():
    """Returns an async callable that dispatches mock responses by URL path."""
    async def mock_get(client, path: str, params: dict) -> dict:
        if path == "/channels":
            return MOCK_CHANNEL_RESPONSE
        if path == "/playlistItems":
            return MOCK_PLAYLIST_RESPONSE
        if path == "/videos":
            return MOCK_VIDEOS_RESPONSE
        return {"items": []}
    return mock_get


@pytest.mark.asyncio
async def test_fetch_channel_videos_returns_correct_count():
    with patch("app.services.youtube_scraper._get", side_effect=_mock_get_factory()):
        from app.services.youtube_scraper import fetch_channel_videos
        videos = await fetch_channel_videos("UCtest123")

    assert len(videos) == 2


@pytest.mark.asyncio
async def test_fetch_channel_videos_correct_fields():
    with patch("app.services.youtube_scraper._get", side_effect=_mock_get_factory()):
        from app.services.youtube_scraper import fetch_channel_videos
        videos = await fetch_channel_videos("UCtest123")

    v = videos[0]
    assert v["video_id"] == "vid1"
    assert v["title"] == "How to Build an AI App"
    assert v["view_count"] == 150000
    assert v["like_count"] == 4200
    assert v["comment_count"] == 310
    assert v["tags"] == ["ai", "python"]
    assert v["channel_id"] == "UCtest123"
    assert v["published_at"] is not None


@pytest.mark.asyncio
async def test_fetch_channel_videos_empty_channel():
    async def mock_get_empty(client, path, params):
        if path == "/channels":
            return {"items": []}
        return {"items": []}

    with patch("app.services.youtube_scraper._get", side_effect=mock_get_empty):
        from app.services.youtube_scraper import fetch_channel_videos
        videos = await fetch_channel_videos("UCnonexistent")

    assert videos == []


@pytest.mark.asyncio
async def test_fetch_channel_videos_parses_published_at():
    with patch("app.services.youtube_scraper._get", side_effect=_mock_get_factory()):
        from app.services.youtube_scraper import fetch_channel_videos
        videos = await fetch_channel_videos("UCtest123")

    from datetime import timezone
    assert videos[0]["published_at"].tzinfo is not None
    assert videos[0]["published_at"].year == 2024
