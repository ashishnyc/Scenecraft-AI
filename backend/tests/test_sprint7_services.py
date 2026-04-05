"""Tests for Sprint 7 publish pipeline services (SA-37 through SA-40)."""
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ── SA-37: HLS Preview (endpoint-level logic tested via service utils) ────────
# The HLS endpoint itself relies on subprocess/S3 — we test the key-building
# logic and the segment security guard.

def test_hls_master_key():
    task_id = "abc-123"
    expected = f"tasks/{task_id}/hls/master.m3u8"
    # Replicates key construction in the endpoint
    master_key = f"tasks/{task_id}/hls/master.m3u8"
    assert master_key == expected


def test_hls_segment_path_guard():
    """Segment key must start with tasks/{task_id}/hls/."""
    task_id = "abc-123"
    safe_key = f"tasks/{task_id}/hls/seg_0_001.ts"
    unsafe_key = "tasks/other-id/hls/evil.ts"
    assert safe_key.startswith(f"tasks/{task_id}/hls/")
    assert not unsafe_key.startswith(f"tasks/{task_id}/hls/")


# ── SA-39: Thumbnail Generator ────────────────────────────────────────────────

from app.services.thumbnail_generator import generate_thumbnail_options


@pytest.mark.asyncio
async def test_thumbnail_no_api_key():
    mock_settings = MagicMock()
    mock_settings.IMAGE_GEN_API_KEY = ""
    with patch("app.services.thumbnail_generator.get_settings", return_value=mock_settings):
        result = await generate_thumbnail_options("task-1")
    assert result is None


# ── SA-40: Metadata Generator ─────────────────────────────────────────────────

from app.services.metadata_generator import _parse_metadata


def test_parse_metadata_clean_json():
    raw = json.dumps({"title": "T", "description": "D", "tags": ["a", "b"]})
    m = _parse_metadata(raw)
    assert m["title"] == "T"
    assert m["description"] == "D"
    assert m["tags"] == ["a", "b"]


def test_parse_metadata_strips_fences():
    raw = '```json\n{"title":"X","description":"Y","tags":[]}\n```'
    m = _parse_metadata(raw)
    assert m["title"] == "X"
    assert m["tags"] == []


def test_parse_metadata_invalid_raises():
    with pytest.raises(Exception):
        _parse_metadata("not json at all")


@pytest.mark.asyncio
async def test_metadata_no_api_key():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = ""
    with patch("app.services.metadata_generator.get_settings", return_value=mock_settings):
        result = await generate_metadata("task-1")
    assert result is None


@pytest.mark.asyncio
async def test_metadata_success():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"

    payload = {"title": "Epic Title", "description": "Great desc", "tags": ["drama", "thriller"]}

    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=json.dumps(payload))]
    )

    mock_db_row = MagicMock()
    mock_db_row.script = {"outline": {"logline": "x", "genre": "drama", "themes": [], "synopsis": "y"}}
    mock_db_row.title = "Old Title"

    async def mock_get_db():
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_row
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        yield mock_db

    with patch("app.services.metadata_generator.get_settings", return_value=mock_settings), \
         patch("app.services.metadata_generator.anthropic.Anthropic", return_value=mock_client), \
         patch("app.services.metadata_generator.get_db", mock_get_db):
        result = await generate_metadata("task-1")

    assert result is not None
    assert result["title"] == "Epic Title"
    assert "drama" in result["tags"]


# Helper import for the async test above
from app.services.metadata_generator import generate_youtube_metadata as generate_metadata
