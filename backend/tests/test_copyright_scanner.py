"""Tests for the copyright scanner (script pipeline stage 4)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.copyright_scanner import (
    CopyrightReport,
    FlaggedSegment,
    _extract_scene_texts,
    _overall_risk,
    scan_copyright,
    COPYRIGHT_THRESHOLD,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_full_script(num_scenes: int = 2) -> dict:
    return {
        "scenes": [
            {
                "scene_number": i,
                "narration": f"Narration for scene {i}.",
                "dialogue": [{"character": "Alex", "line": f"Line {i}."}],
                "visual_direction": "Wide shot.",
                "estimated_duration_seconds": 60,
            }
            for i in range(1, num_scenes + 1)
        ]
    }


def _scored_point(score: float, title: str = "Some Video") -> MagicMock:
    pt = MagicMock()
    pt.score = score
    pt.payload = {"title": title, "video_id": "abc"}
    return pt


# ── Unit: helpers ─────────────────────────────────────────────────────────────

class TestExtractSceneTexts:
    def test_extracts_narration_and_dialogue(self):
        script = _make_full_script(2)
        texts = _extract_scene_texts(script)
        assert len(texts) == 2
        assert all(isinstance(t[1], str) and len(t[1]) > 0 for t in texts)

    def test_empty_scenes_returns_empty(self):
        assert _extract_scene_texts({"scenes": []}) == []

    def test_scene_with_no_text_excluded(self):
        script = {"scenes": [{"scene_number": 1, "narration": "", "dialogue": [],
                               "visual_direction": "x", "estimated_duration_seconds": 30}]}
        assert _extract_scene_texts(script) == []


class TestOverallRisk:
    def test_zero_score_is_low(self):
        assert _overall_risk(0.0) == "low"

    def test_medium_threshold(self):
        assert _overall_risk(0.5) == "medium"

    def test_high_threshold(self):
        assert _overall_risk(0.85) == "high"


class TestCopyrightReport:
    def test_no_flags_is_clear(self):
        report = CopyrightReport(flagged_segments=[], overall_risk_level="low")
        assert report.is_clear is True

    def test_flagged_is_not_clear(self):
        flag = FlaggedSegment(scene_number=1, text="x", similarity_score=0.9, source="video")
        report = CopyrightReport(flagged_segments=[flag], overall_risk_level="high")
        assert report.is_clear is False


# ── Integration: scan_copyright ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_no_api_key():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = ""
    with patch("app.services.copyright_scanner.get_settings", return_value=mock_settings):
        result = await scan_copyright("t-1", _make_full_script(), "ws-1")
    assert result is None


@pytest.mark.asyncio
async def test_scan_no_similar_results():
    """Qdrant returns nothing → no flags, script unchanged."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"

    with patch("app.services.copyright_scanner.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=MagicMock()), \
         patch("app.services.copyright_scanner.search_similar", AsyncMock(return_value=[])):
        result = await scan_copyright("t-1", _make_full_script(2), "ws-1")

    assert result is not None
    updated_script, report = result
    assert report["flagged_segments"] == []
    assert report["overall_risk_level"] == "low"
    assert len(updated_script["scenes"]) == 2


@pytest.mark.asyncio
async def test_scan_below_threshold_not_flagged():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"
    low_score = _scored_point(COPYRIGHT_THRESHOLD - 0.01)

    with patch("app.services.copyright_scanner.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=MagicMock()), \
         patch("app.services.copyright_scanner.search_similar", AsyncMock(return_value=[low_score])):
        result = await scan_copyright("t-1", _make_full_script(1), "ws-1")

    assert result is not None
    _, report = result
    assert report["flagged_segments"] == []


@pytest.mark.asyncio
async def test_scan_above_threshold_flagged_and_rewritten():
    """Scenes above threshold are flagged and the LLM rewrites them."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"
    high_score = _scored_point(0.95, "Stolen Video")

    rewritten_scene = {
        "scene_number": 1,
        "narration": "Completely original narration.",
        "dialogue": [],
        "visual_direction": "New angle.",
        "estimated_duration_seconds": 55,
    }
    import json
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=json.dumps(rewritten_scene))]
    )

    with patch("app.services.copyright_scanner.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client), \
         patch("app.services.copyright_scanner.search_similar", AsyncMock(return_value=[high_score])):
        result = await scan_copyright("t-1", _make_full_script(1), "ws-1")

    assert result is not None
    updated_script, report = result
    assert len(report["flagged_segments"]) == 1
    assert report["flagged_segments"][0]["source"] == "Stolen Video"
    assert report["overall_risk_level"] == "high"
    # Verify scene was rewritten
    assert updated_script["scenes"][0]["narration"] == "Completely original narration."


@pytest.mark.asyncio
async def test_scan_qdrant_failure_skips_scene():
    """Qdrant error on a scene is logged and skipped; scan still completes."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"

    with patch("app.services.copyright_scanner.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=MagicMock()), \
         patch("app.services.copyright_scanner.search_similar",
               AsyncMock(side_effect=Exception("qdrant down"))):
        result = await scan_copyright("t-1", _make_full_script(2), "ws-1")

    assert result is not None
    _, report = result
    assert report["flagged_segments"] == []
