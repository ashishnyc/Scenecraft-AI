"""Unit and integration tests for pitch generator."""
import json
import pytest
from pydantic import ValidationError
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.pitch import PitchData
from app.services.pitch_generator import _parse_llm_response, _build_user_prompt


# ─── Schema validation tests ─────────────────────────────────────────────────

class TestPitchDataValidation:
    def _valid(self, **overrides):
        base = {
            "title": "Why AI is Taking Over YouTube",
            "concept_summary": "This video explores how AI tools are being used by creators "
                               "to automate scripting, voice cloning, and thumbnail generation. "
                               "We cover five real-world examples with view counts.",
            "target_audience_hook": "If you make YouTube videos, AI will either be your biggest "
                                    "competitor or your best tool — find out which.",
            "appeal_score": 8.5,
        }
        base.update(overrides)
        return base

    def test_valid_pitch_passes(self):
        pd = PitchData(**self._valid())
        assert pd.title == "Why AI is Taking Over YouTube"
        assert pd.appeal_score == 8.5

    def test_empty_title_fails(self):
        with pytest.raises(ValidationError):
            PitchData(**self._valid(title=""))

    def test_title_too_short_fails(self):
        with pytest.raises(ValidationError):
            PitchData(**self._valid(title="Ab"))

    def test_concept_too_short_fails(self):
        with pytest.raises(ValidationError):
            PitchData(**self._valid(concept_summary="Too short."))

    def test_appeal_score_above_10_fails(self):
        with pytest.raises(ValidationError):
            PitchData(**self._valid(appeal_score=10.1))

    def test_appeal_score_below_0_fails(self):
        with pytest.raises(ValidationError):
            PitchData(**self._valid(appeal_score=-0.1))

    def test_optional_fields_can_be_none(self):
        pd = PitchData(**self._valid(target_audience_hook=None, appeal_score=None))
        assert pd.target_audience_hook is None
        assert pd.appeal_score is None

    def test_concept_word_count_enforced(self):
        # 9 words — fails validator
        with pytest.raises(ValidationError):
            PitchData(**self._valid(concept_summary="One two three four five six seven eight nine."))


# ─── LLM output parsing ───────────────────────────────────────────────────────

VALID_PITCH_JSON = json.dumps([{
    "title": "AI Shorts That Go Viral",
    "concept_summary": (
        "Explore the exact format used by the top ten AI channels to produce "
        "short-form content that consistently hits one million views. We break "
        "down hooks, pacing, and thumbnail strategy used in viral AI videos."
    ),
    "target_audience_hook": "You are one formula away from your first viral video.",
    "appeal_score": 9.0,
}])


class TestParseLLMResponse:
    def test_valid_json_array_parsed(self):
        pitches = _parse_llm_response(VALID_PITCH_JSON)
        assert len(pitches) == 1
        assert pitches[0].title == "AI Shorts That Go Viral"

    def test_markdown_fenced_json_stripped(self):
        fenced = f"```json\n{VALID_PITCH_JSON}\n```"
        pitches = _parse_llm_response(fenced)
        assert len(pitches) == 1

    def test_invalid_pitch_skipped_not_crashed(self):
        mixed = json.dumps([
            {"title": "", "concept_summary": "short", "appeal_score": 5},  # invalid
            json.loads(VALID_PITCH_JSON)[0],  # valid
        ])
        pitches = _parse_llm_response(mixed)
        assert len(pitches) == 1  # only the valid one

    def test_single_object_not_array(self):
        single = json.dumps(json.loads(VALID_PITCH_JSON)[0])
        pitches = _parse_llm_response(single)
        assert len(pitches) == 1


# ─── Prompt builder ───────────────────────────────────────────────────────────

class TestBuildUserPrompt:
    def test_includes_workspace_name(self):
        prompt = _build_user_prompt("Horror Channel", {}, [], [], 3)
        assert "Horror Channel" in prompt

    def test_includes_count(self):
        prompt = _build_user_prompt("WS", {}, [], [], 5)
        assert "5" in prompt

    def test_includes_trending_topics(self):
        topics = [{"topic": "Haunted Hotels", "score": 0.8, "source": "reddit"}]
        prompt = _build_user_prompt("WS", {}, topics, [], 3)
        assert "Haunted Hotels" in prompt

    def test_includes_competitor_videos(self):
        videos = [{"title": "Top 10 Scary Hotels", "view_count": 2_000_000}]
        prompt = _build_user_prompt("WS", {}, [], videos, 3)
        assert "Top 10 Scary Hotels" in prompt


# ─── generate_pitches integration (LLM mocked) ───────────────────────────────

@pytest.mark.asyncio
async def test_generate_pitches_saves_to_db():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=VALID_PITCH_JSON)]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "test-key"

    with patch("app.core.config.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client):
        from app.services.pitch_generator import generate_pitches
        pitches = await generate_pitches(
            workspace_id="00000000-0000-0000-0000-000000000001",
            workspace_name="Test WS",
            style_guide={},
            trending_topics=[],
            competitor_top_videos=[],
            db=mock_db,
            count=1,
        )

    assert len(pitches) == 1
    assert mock_db.add.called
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_generate_pitches_skips_when_no_api_key():
    mock_db = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = ""

    with patch("app.core.config.get_settings", return_value=mock_settings):
        from app.services.pitch_generator import generate_pitches
        pitches = await generate_pitches(
            workspace_id="00000000-0000-0000-0000-000000000001",
            workspace_name="Test WS",
            style_guide={},
            trending_topics=[],
            competitor_top_videos=[],
            db=mock_db,
            count=1,
        )

    assert pitches == []
    assert not mock_db.add.called
