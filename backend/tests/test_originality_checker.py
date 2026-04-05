"""Unit and integration tests for the originality checker."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.originality_checker import (
    compute_originality_score,
    is_low_originality,
    check_pitch_originality,
)


# ─── Unit tests for threshold logic ──────────────────────────────────────────

class TestComputeOriginalityScore:
    def test_zero_similarity_gives_full_originality(self):
        assert compute_originality_score(0.0) == 1.0

    def test_full_similarity_gives_zero_originality(self):
        assert compute_originality_score(1.0) == 0.0

    def test_mid_similarity(self):
        assert compute_originality_score(0.5) == 0.5

    def test_clamped_above_1(self):
        assert compute_originality_score(1.5) == 0.0

    def test_clamped_below_0(self):
        assert compute_originality_score(-0.2) == 1.0

    def test_result_rounded_to_4dp(self):
        score = compute_originality_score(0.12345678)
        assert len(str(score).split(".")[-1]) <= 4


class TestIsLowOriginality:
    def test_above_threshold_is_low(self):
        assert is_low_originality(0.90, threshold=0.85) is True

    def test_at_threshold_is_low(self):
        assert is_low_originality(0.85, threshold=0.85) is True

    def test_below_threshold_is_original(self):
        assert is_low_originality(0.84, threshold=0.85) is False

    def test_zero_similarity_is_original(self):
        assert is_low_originality(0.0, threshold=0.85) is False

    def test_uses_settings_threshold_when_none_given(self):
        mock_settings = MagicMock()
        mock_settings.ORIGINALITY_THRESHOLD = 0.75
        with patch("app.services.originality_checker.get_settings", return_value=mock_settings):
            assert is_low_originality(0.80) is True
            assert is_low_originality(0.70) is False


# ─── Integration: check_pitch_originality ────────────────────────────────────

@pytest.mark.asyncio
async def test_check_pitch_originality_no_results():
    """When Qdrant returns no results, pitch is fully original."""
    with patch("app.services.originality_checker.search_similar", new=AsyncMock(return_value=[])):
        result = await check_pitch_originality("Some pitch text", "ws-1")

    assert result["originality_score"] == 1.0
    assert result["max_similarity"] == 0.0
    assert result["low_originality"] is False
    assert result["similar_videos"] == []


@pytest.mark.asyncio
async def test_check_pitch_originality_low_similarity():
    """Similarity below threshold → pitch is original."""
    mock_point = MagicMock()
    mock_point.score = 0.60
    mock_point.payload = {"title": "Some Video", "video_id": "abc123"}

    with patch("app.services.originality_checker.search_similar", new=AsyncMock(return_value=[mock_point])):
        result = await check_pitch_originality("Original concept", "ws-1")

    assert result["originality_score"] == 0.4
    assert result["low_originality"] is False
    assert len(result["similar_videos"]) == 1


@pytest.mark.asyncio
async def test_check_pitch_originality_high_similarity():
    """Similarity at or above threshold → low_originality = True."""
    mock_point = MagicMock()
    mock_point.score = 0.92
    mock_point.payload = {"title": "Very Similar Video", "video_id": "xyz789"}

    mock_settings = MagicMock()
    mock_settings.ORIGINALITY_THRESHOLD = 0.85

    with patch("app.services.originality_checker.search_similar", new=AsyncMock(return_value=[mock_point])), \
         patch("app.services.originality_checker.get_settings", return_value=mock_settings):
        result = await check_pitch_originality("Copied concept", "ws-1")

    assert result["low_originality"] is True
    assert result["originality_score"] < 0.1


@pytest.mark.asyncio
async def test_check_pitch_originality_qdrant_error_defaults_to_original():
    """If Qdrant search fails, assume the pitch is original (fail open)."""
    with patch("app.services.originality_checker.search_similar", new=AsyncMock(side_effect=Exception("Qdrant down"))):
        result = await check_pitch_originality("Any text", "ws-1")

    assert result["originality_score"] == 1.0
    assert result["low_originality"] is False


# ─── Integration: Qdrant in-memory upsert + search ───────────────────────────

@pytest.mark.asyncio
async def test_qdrant_upsert_and_search():
    """
    End-to-end: upsert known embeddings into in-memory Qdrant,
    then verify similarity search returns the right video.
    """
    from qdrant_client import AsyncQdrantClient
    from app.services.vector_store import upsert_videos, search_similar, COLLECTION_NAME
    from app.db.qdrant import ensure_collection

    # Use a fresh in-memory client for this test
    test_client = AsyncQdrantClient(":memory:")

    videos = [
        {
            "video_id": "v1",
            "title": "How to build a haunted house YouTube channel",
            "description": "Step-by-step guide for horror content creators",
            "workspace_id": "ws-test",
            "channel_id": "ch1",
        },
        {
            "video_id": "v2",
            "title": "Best cooking recipes for beginners",
            "description": "Easy meals you can make at home",
            "workspace_id": "ws-test",
            "channel_id": "ch1",
        },
    ]

    with patch("app.services.vector_store.get_qdrant_client", return_value=test_client):
        await upsert_videos(videos)
        results = await search_similar(
            "haunted house horror content channel",
            "ws-test",
            limit=2,
        )

    assert len(results) >= 1
    top = results[0]
    assert top.payload["video_id"] == "v1"
    assert top.score > 0.5
