"""Tests for Sprint 8 publish & analytics services (SA-41 through SA-47)."""
import json
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ── SA-41: Scene Re-editor ────────────────────────────────────────────────────

from app.services.scene_re_editor import re_edit_flagged_scenes


@pytest.mark.asyncio
async def test_re_edit_no_flagged_shots_returns_existing_qc():
    """When no shots are flagged, returns existing quality_report without re-generating."""
    mock_row = MagicMock()
    mock_row.script = {
        "shot_list": {"shots": [{"shot_index": 0, "duration_seconds": 5}]},
        "clip_urls": {"0": "s3://bucket/0.mp4"},
        "video_review": {"flagged_shot_indices": []},
        "quality_report": {"passed": True, "errors": []},
    }
    mock_row.title = "Test"

    async def mock_get_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_row
        db.execute = AsyncMock(return_value=result)
        yield db

    with patch("app.services.scene_re_editor.get_db", mock_get_db):
        result = await re_edit_flagged_scenes("task-1")

    assert result == {"passed": True, "errors": []}


# ── SA-42: Audit Trail ────────────────────────────────────────────────────────
# ReviewAction model already exists — SA-42 is wired in tasks.py transitions.
# We test the model directly.

from app.models.review_action import ReviewAction, ReviewActionType


def test_review_action_type_values():
    assert ReviewActionType.approve == "approve"
    assert ReviewActionType.request_changes == "request_changes"


# ── SA-43: YouTube Uploader ───────────────────────────────────────────────────

from app.services.youtube_uploader import upload_to_youtube


@pytest.mark.asyncio
async def test_youtube_upload_no_api_key():
    mock_settings = MagicMock()
    mock_settings.YOUTUBE_API_KEY = ""
    with patch("app.services.youtube_uploader.get_settings", return_value=mock_settings):
        result = await upload_to_youtube("task-1")
    assert result is None


# ── SA-44: Upload Scheduler ───────────────────────────────────────────────────

from app.services.upload_scheduler import suggest_best_publish_time


@pytest.mark.asyncio
async def test_suggest_best_publish_time_fallback():
    """Without YOUTUBE_API_KEY, should return a future datetime."""
    mock_settings = MagicMock()
    mock_settings.YOUTUBE_API_KEY = ""

    with patch("app.services.upload_scheduler.get_settings", return_value=mock_settings):
        suggested = await suggest_best_publish_time("task-1")

    assert isinstance(suggested, datetime)
    assert suggested > datetime.now(timezone.utc)


# ── SA-45: Analytics Tracker ─────────────────────────────────────────────────

from app.services.analytics_tracker import compute_retention_curve


def test_compute_retention_curve_empty():
    assert compute_retention_curve({}) == []


def test_compute_retention_curve_basic():
    metrics = {
        "history": [
            {"polled_at": "2025-01-01T00:00:00+00:00", "views": 100, "likes": 10},
            {"polled_at": "2025-01-02T00:00:00+00:00", "views": 200, "likes": 20},
            {"polled_at": "2025-01-03T00:00:00+00:00", "views": 350, "likes": 30},
        ]
    }
    curve = compute_retention_curve(metrics)
    assert len(curve) == 3
    assert curve[0]["views"] == 100
    assert curve[0]["view_growth_pct"] == 0.0   # first point, no prior
    assert curve[1]["view_growth_pct"] == 100.0  # 100→200 = 100% growth
    assert curve[2]["view_growth_pct"] == 75.0   # 200→350 = 75% growth


# ── SA-47: Feedback Loop ──────────────────────────────────────────────────────

from app.services.feedback_loop import compute_content_score


def test_compute_content_score_no_data():
    score = compute_content_score({})
    assert 0.0 <= score <= 1.0


def test_compute_content_score_high_performer():
    metrics = {
        "latest": {"views": 50000, "likes": 3000, "average_view_percentage": 80.0},
        "history": [
            {"views": i * 1000} for i in range(1, 52)
        ],
    }
    score = compute_content_score(metrics)
    assert score > 0.3  # well-performing video


def test_compute_content_score_clamped():
    # Extremely high numbers should still stay ≤ 1.0
    metrics = {
        "latest": {"views": 10_000_000, "likes": 1_000_000, "average_view_percentage": 100.0},
        "history": [],
    }
    assert compute_content_score(metrics) <= 1.0
