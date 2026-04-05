"""Unit and integration tests for the outline generator."""
import json
import pytest
from unittest.mock import MagicMock, patch

from app.services.outline_generator import (
    Outline,
    Act,
    Scene,
    _parse_outline,
    generate_outline,
)


# ── Unit: schema validation ───────────────────────────────────────────────────

class TestOutlineSchema:
    def _valid_outline_dict(self):
        return {
            "acts": [
                {
                    "act_number": i,
                    "title": f"Act {i} Title",
                    "scenes": [
                        {
                            "scene_number": (i - 1) * 3 + j,
                            "location": "Office",
                            "time_of_day": "Day",
                            "summary": "Something happens here that moves the story forward.",
                            "characters_present": ["Alice"],
                        }
                        for j in range(1, 4)
                    ],
                }
                for i in range(1, 4)
            ]
        }

    def test_valid_outline_parses(self):
        data = self._valid_outline_dict()
        outline = Outline(**data)
        assert len(outline.acts) == 3

    def test_wrong_act_count_raises(self):
        data = self._valid_outline_dict()
        data["acts"] = data["acts"][:2]  # only 2 acts
        with pytest.raises(ValueError, match="exactly 3 acts"):
            Outline(**data)

    def test_too_few_scenes_raises(self):
        data = self._valid_outline_dict()
        data["acts"][0]["scenes"] = data["acts"][0]["scenes"][:2]  # only 2 scenes
        with pytest.raises(ValueError, match="at least 3 scenes"):
            Outline(**data)

    def test_missing_scene_fields_raises(self):
        data = self._valid_outline_dict()
        del data["acts"][0]["scenes"][0]["location"]
        with pytest.raises(Exception):
            Outline(**data)

    def test_missing_acts_key_raises(self):
        with pytest.raises(Exception):
            Outline(**{"not_acts": []})

    def test_scene_characters_defaults_to_empty(self):
        data = self._valid_outline_dict()
        for act in data["acts"]:
            for scene in act["scenes"]:
                del scene["characters_present"]
        outline = Outline(**data)
        assert outline.acts[0].scenes[0].characters_present == []


class TestParseOutline:
    def _raw_json(self):
        outline = {
            "acts": [
                {
                    "act_number": i,
                    "title": f"Act {i}",
                    "scenes": [
                        {
                            "scene_number": (i - 1) * 3 + j,
                            "location": "Park",
                            "time_of_day": "Day",
                            "summary": "Scene summary goes here for the test.",
                            "characters_present": [],
                        }
                        for j in range(1, 4)
                    ],
                }
                for i in range(1, 4)
            ]
        }
        return json.dumps(outline)

    def test_plain_json_parses(self):
        raw = self._raw_json()
        outline = _parse_outline(raw)
        assert len(outline.acts) == 3

    def test_markdown_fences_stripped(self):
        raw = f"```json\n{self._raw_json()}\n```"
        outline = _parse_outline(raw)
        assert len(outline.acts) == 3

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            _parse_outline("not json at all")

    def test_invalid_schema_raises(self):
        with pytest.raises(Exception):
            _parse_outline('{"acts": []}')  # 0 acts → validation error

    def test_unlisted_character_raises(self):
        outline = {
            "acts": [
                {
                    "act_number": i,
                    "title": f"Act {i}",
                    "scenes": [
                        {
                            "scene_number": (i - 1) * 3 + j,
                            "location": "Park",
                            "time_of_day": "Day",
                            "summary": "Scene summary.",
                            "characters_present": ["Ghost"],  # not in cast
                        }
                        for j in range(1, 4)
                    ],
                }
                for i in range(1, 4)
            ]
        }
        with pytest.raises(ValueError, match="not in the project cast"):
            _parse_outline(json.dumps(outline), cast_names=["Alice"])

    def test_valid_cast_passes(self):
        outline = {
            "acts": [
                {
                    "act_number": i,
                    "title": f"Act {i}",
                    "scenes": [
                        {
                            "scene_number": (i - 1) * 3 + j,
                            "location": "Park",
                            "time_of_day": "Day",
                            "summary": "Scene summary.",
                            "characters_present": ["Alice"],
                        }
                        for j in range(1, 4)
                    ],
                }
                for i in range(1, 4)
            ]
        }
        result = _parse_outline(json.dumps(outline), cast_names=["Alice", "Bob"])
        assert len(result.acts) == 3


# ── Integration: generate_outline with mocked LLM ────────────────────────────

def _make_valid_raw():
    outline = {
        "acts": [
            {
                "act_number": i,
                "title": f"Act {i}: The Journey",
                "scenes": [
                    {
                        "scene_number": (i - 1) * 4 + j,
                        "location": "Haunted House",
                        "time_of_day": "Night",
                        "summary": "Our heroes explore the darkened corridor, hearing strange sounds.",
                        "characters_present": ["Alex", "Jordan"],
                    }
                    for j in range(1, 5)
                ],
            }
            for i in range(1, 4)
        ]
    }
    return json.dumps(outline)


@pytest.mark.asyncio
async def test_generate_outline_no_api_key():
    """Without API key, generate_outline returns None gracefully."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = ""
    with patch("app.services.outline_generator.get_settings", return_value=mock_settings):
        result = await generate_outline(
            task_id="t-1",
            concept_brief="A horror house tour",
            creator_notes=None,
            style_guide={},
            cast_names=["Alex", "Jordan"],
        )
    assert result is None


@pytest.mark.asyncio
async def test_generate_outline_stores_valid_outline():
    """With a valid LLM mock response, returns a validated outline dict."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=_make_valid_raw())]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("app.services.outline_generator.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = await generate_outline(
            task_id="t-1",
            concept_brief="A horror house channel tour",
            creator_notes="Make it spooky",
            style_guide={"tone": "dark"},
            cast_names=["Alex", "Jordan"],
        )

    assert result is not None
    assert "acts" in result
    assert len(result["acts"]) == 3
    for act in result["acts"]:
        assert len(act["scenes"]) >= 3


@pytest.mark.asyncio
async def test_generate_outline_llm_error_returns_none():
    """LLM call failure returns None without raising."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API timeout")

    with patch("app.services.outline_generator.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = await generate_outline(
            task_id="t-1",
            concept_brief="Horror content",
            creator_notes=None,
            style_guide={},
            cast_names=[],
        )
    assert result is None


@pytest.mark.asyncio
async def test_generate_outline_bad_json_returns_none():
    """Malformed LLM output returns None without raising."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"acts": "oops"}')]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("app.services.outline_generator.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = await generate_outline(
            task_id="t-1",
            concept_brief="Horror content",
            creator_notes=None,
            style_guide={},
            cast_names=[],
        )
    assert result is None
