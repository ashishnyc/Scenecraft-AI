"""Tests for Sprint 6 video pipeline services (SA-30 through SA-36)."""
import json
import math
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── SA-30: Scene Planner ──────────────────────────────────────────────────────

from app.services.scene_planner import Shot, ShotList, _parse_shot_list, plan_shots


def _valid_shot_list_raw(num_shots: int = 4) -> str:
    shots = [
        {
            "shot_index": i,
            "scene_number": 1,
            "duration_seconds": 5.0,
            "characters": ["Alex"],
            "environment": "Manor hallway",
            "camera_angle": "wide",
            "action_description": f"Action {i}",
            "mood": "tense",
        }
        for i in range(num_shots)
    ]
    return json.dumps({"shots": shots})


class TestShotSchema:
    def test_valid_shot(self):
        shot = Shot(shot_index=0, scene_number=1, duration_seconds=5.0,
                    environment="x", camera_angle="wide", action_description="y", mood="tense")
        assert shot.duration_seconds == 5.0

    def test_duration_below_min_raises(self):
        with pytest.raises(Exception):
            Shot(shot_index=0, scene_number=1, duration_seconds=2.0,
                 environment="x", camera_angle="w", action_description="y", mood="m")

    def test_duration_above_max_raises(self):
        with pytest.raises(Exception):
            Shot(shot_index=0, scene_number=1, duration_seconds=15.0,
                 environment="x", camera_angle="w", action_description="y", mood="m")

    def test_empty_shot_list_raises(self):
        with pytest.raises(ValueError):
            ShotList(shots=[])


class TestParseShotList:
    def test_valid_parses(self):
        sl = _parse_shot_list(_valid_shot_list_raw(3))
        assert len(sl.shots) == 3

    def test_markdown_fences_stripped(self):
        raw = f"```json\n{_valid_shot_list_raw(2)}\n```"
        sl = _parse_shot_list(raw)
        assert len(sl.shots) == 2

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            _parse_shot_list("not json")


@pytest.mark.asyncio
async def test_plan_shots_no_api_key():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = ""
    with patch("app.services.scene_planner.get_settings", return_value=mock_settings):
        result = await plan_shots("t-1", {"scenes": []}, None)
    assert result is None


@pytest.mark.asyncio
async def test_plan_shots_success():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=_valid_shot_list_raw(6))]
    )
    with patch("app.services.scene_planner.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = await plan_shots("t-1", {"scenes": [{"scene_number": 1, "narration": "x"}]}, None)
    assert result is not None
    assert len(result["shots"]) == 6


# ── SA-31: Character Consistency ─────────────────────────────────────────────

from app.services.character_consistency import (
    build_character_reference_prompt,
    build_cast_reference_prompts,
    inject_character_references,
    check_clip_similarity,
    flag_low_similarity_shots,
)


def test_reference_prompt_includes_lora():
    prompt = build_character_reference_prompt(
        "Alex",
        personality_prompt="brave",
        visual_references={"base_description": "tall", "lora_trigger_words": "alex_v1"},
        appearance_override=None,
    )
    assert "alex_v1" in prompt
    assert "Alex" in prompt


def test_reference_prompt_appearance_override():
    prompt = build_character_reference_prompt(
        "Alex", None, None, {"hair": "short"}
    )
    assert "hair" in prompt


def test_build_cast_reference_prompts():
    cast = [{"name": "Alex", "personality_prompt": "x", "visual_references": None, "appearance_override": None}]
    refs = build_cast_reference_prompts(cast)
    assert "Alex" in refs


def test_inject_character_references_appends():
    refs = {"Alex": "ALEX_REF"}
    result = inject_character_references("base prompt", ["Alex"], refs)
    assert "ALEX_REF" in result
    assert "base prompt" in result


def test_inject_no_characters_unchanged():
    result = inject_character_references("base prompt", [], {})
    assert result == "base prompt"


def test_clip_similarity_identical_vectors():
    v = [1.0, 0.0, 0.0]
    assert math.isclose(check_clip_similarity(v, v), 1.0)


def test_clip_similarity_orthogonal_vectors():
    score = check_clip_similarity([1.0, 0.0], [0.0, 1.0])
    assert math.isclose(score, 0.0)


def test_flag_low_similarity_shots():
    similarities = {0: 0.9, 1: 0.6, 2: 0.8, 3: 0.5}
    flagged = flag_low_similarity_shots(similarities, threshold=0.75)
    assert sorted(flagged) == [1, 3]


# ── SA-32: Environment Generator ─────────────────────────────────────────────

from app.services.environment_generator import (
    extract_unique_environments,
    _env_slug,
)


def _shot_list_with_envs(envs: list[str]) -> dict:
    return {
        "shots": [
            {"shot_index": i, "scene_number": 1, "environment": env,
             "duration_seconds": 5.0, "characters": [], "camera_angle": "wide",
             "action_description": "x", "mood": "neutral"}
            for i, env in enumerate(envs)
        ]
    }


def test_extract_unique_environments_deduplicates():
    shot_list = _shot_list_with_envs(["Manor", "Basement", "Manor", "Garden"])
    envs = extract_unique_environments(shot_list)
    assert envs == ["Manor", "Basement", "Garden"]


def test_env_slug_normalises():
    assert _env_slug("Victorian Manor Hallway!") == "victorian_manor_hallway_"
    assert len(_env_slug("x" * 100)) <= 64


# ── SA-34: Music Generator ────────────────────────────────────────────────────

from app.services.music_generator import extract_scene_moods


def test_extract_scene_moods():
    shot_list = {
        "shots": [
            {"shot_index": 0, "scene_number": 1, "mood": "tense", "duration_seconds": 5.0,
             "environment": "x", "camera_angle": "w", "action_description": "y", "characters": []},
            {"shot_index": 1, "scene_number": 1, "mood": "mysterious", "duration_seconds": 5.0,
             "environment": "x", "camera_angle": "w", "action_description": "y", "characters": []},
            {"shot_index": 2, "scene_number": 2, "mood": "hopeful", "duration_seconds": 5.0,
             "environment": "x", "camera_angle": "w", "action_description": "y", "characters": []},
        ]
    }
    moods = extract_scene_moods(shot_list)
    assert set(moods[1]) == {"tense", "mysterious"}
    assert moods[2] == ["hopeful"]


# ── SA-35: Video Assembler ────────────────────────────────────────────────────

from app.services.video_assembler import calculate_timeline


def test_calculate_timeline_sequential():
    shot_list = {
        "shots": [
            {"shot_index": 0, "scene_number": 1, "duration_seconds": 5.0},
            {"shot_index": 1, "scene_number": 1, "duration_seconds": 7.0},
            {"shot_index": 2, "scene_number": 2, "duration_seconds": 4.0},
        ]
    }
    timeline = calculate_timeline(shot_list, None)
    assert timeline[0] == 0.0
    assert timeline[1] == 5.0
    assert timeline[2] == 12.0


def test_calculate_timeline_empty():
    assert calculate_timeline({"shots": []}, None) == {}


# ── SA-36: Quality Checker ────────────────────────────────────────────────────

from app.services.video_quality_checker import (
    QualityReport,
    check_video_quality,
    _parse_framerate,
)


def test_parse_framerate():
    assert math.isclose(_parse_framerate("24/1"), 24.0)
    assert math.isclose(_parse_framerate("30000/1001"), 29.97, rel_tol=0.01)
    assert _parse_framerate("invalid") == 0.0


def test_quality_report_to_dict():
    r = QualityReport(passed=True, errors=[], warnings=["w"])
    d = r.to_dict()
    assert d["passed"] is True
    assert d["warnings"] == ["w"]


def test_check_video_quality_ffprobe_failure():
    """When ffprobe fails, report is failed with error."""
    with patch("app.services.video_quality_checker._run_ffprobe", side_effect=Exception("no ffprobe")):
        report = check_video_quality("/fake/path.mp4")
    assert not report.passed
    assert any("ffprobe" in e for e in report.errors)


def test_check_video_quality_wrong_resolution():
    probe_data = {
        "streams": [{"width": 1280, "height": 720, "codec_name": "h264",
                     "r_frame_rate": "30/1", "codec_type": "video"}],
        "format": {"duration": "60.0"},
    }
    with patch("app.services.video_quality_checker._run_ffprobe", return_value=probe_data), \
         patch("app.services.video_quality_checker._detect_black_frames", return_value=[]):
        report = check_video_quality("/fake/path.mp4")
    assert not report.passed
    assert any("1280x720" in e for e in report.errors)


def test_check_video_quality_passes():
    probe_data = {
        "streams": [{"width": 1920, "height": 1080, "codec_name": "h264",
                     "r_frame_rate": "24/1", "codec_type": "video"}],
        "format": {"duration": "60.0"},
    }
    with patch("app.services.video_quality_checker._run_ffprobe", return_value=probe_data), \
         patch("app.services.video_quality_checker._detect_black_frames", return_value=[]):
        report = check_video_quality("/fake/path.mp4")
    assert report.passed
    assert report.errors == []
