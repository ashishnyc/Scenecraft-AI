"""Unit and integration tests for the scene expander (script pipeline stage 2)."""
import json
import pytest
from unittest.mock import MagicMock, patch

from app.services.scene_expander import (
    DialogueLine,
    ExpandedScene,
    FullScript,
    _parse_expanded_scene,
    expand_scenes,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_scene_dict(
    scene_number: int = 1,
    characters: list[str] | None = None,
) -> dict:
    return {
        "scene_number": scene_number,
        "narration": "The camera pans across the haunted hallway.",
        "dialogue": [{"character": c, "line": "Hello there."} for c in (characters or [])],
        "visual_direction": "Wide shot, foggy atmosphere, low angle.",
        "estimated_duration_seconds": 60,
    }


def _make_outline(num_scenes: int = 3) -> dict:
    """Minimal outline with a single act containing *num_scenes* scenes."""
    return {
        "acts": [
            {
                "act_number": 1,
                "title": "The Beginning",
                "scenes": [
                    {
                        "scene_number": i,
                        "location": "Haunted House",
                        "time_of_day": "Night",
                        "summary": f"Scene {i}: something spooky happens.",
                        "characters_present": ["Alex"],
                    }
                    for i in range(1, num_scenes + 1)
                ],
            }
        ]
    }


def _raw_scene(scene_number: int = 1, character: str = "Alex") -> str:
    return json.dumps(_make_scene_dict(scene_number, [character]))


# ── Unit: ExpandedScene schema ────────────────────────────────────────────────

class TestExpandedSceneSchema:
    def test_valid_scene_parses(self):
        scene = ExpandedScene(**_make_scene_dict(1, ["Alice"]))
        assert scene.scene_number == 1
        assert len(scene.dialogue) == 1

    def test_empty_dialogue_allowed(self):
        data = _make_scene_dict(1)
        data["dialogue"] = []
        scene = ExpandedScene(**data)
        assert scene.dialogue == []

    def test_missing_narration_raises(self):
        data = _make_scene_dict(1)
        del data["narration"]
        with pytest.raises(Exception):
            ExpandedScene(**data)

    def test_missing_visual_direction_raises(self):
        data = _make_scene_dict(1)
        del data["visual_direction"]
        with pytest.raises(Exception):
            ExpandedScene(**data)


class TestFullScriptSchema:
    def test_valid_full_script(self):
        fs = FullScript(scenes=[ExpandedScene(**_make_scene_dict(i)) for i in range(1, 4)])
        assert len(fs.scenes) == 3

    def test_empty_scenes_raises(self):
        with pytest.raises(ValueError, match="at least one scene"):
            FullScript(scenes=[])


# ── Unit: _parse_expanded_scene ───────────────────────────────────────────────

class TestParseExpandedScene:
    def test_valid_json_parses(self):
        raw = _raw_scene(1, "Alex")
        scene = _parse_expanded_scene(raw, cast_names=["Alex"])
        assert scene.scene_number == 1

    def test_markdown_fences_stripped(self):
        raw = f"```json\n{_raw_scene(1, 'Alex')}\n```"
        scene = _parse_expanded_scene(raw, cast_names=["Alex"])
        assert scene.scene_number == 1

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            _parse_expanded_scene("not json", cast_names=[])

    def test_unlisted_character_in_dialogue_raises(self):
        raw = _raw_scene(1, "Ghost")
        with pytest.raises(ValueError, match="not in the project cast"):
            _parse_expanded_scene(raw, cast_names=["Alex"])

    def test_cast_check_is_case_insensitive(self):
        raw = _raw_scene(1, "ALEX")
        scene = _parse_expanded_scene(raw, cast_names=["alex"])
        assert scene.dialogue[0].character == "ALEX"

    def test_no_cast_skips_validation(self):
        raw = _raw_scene(1, "Anyone")
        scene = _parse_expanded_scene(raw, cast_names=[])
        assert scene.dialogue[0].character == "Anyone"


# ── Integration: expand_scenes with mocked LLM ───────────────────────────────

def _make_mock_client(responses: list[str]) -> MagicMock:
    """Returns a mock Anthropic client that yields *responses* in order."""
    client = MagicMock()
    messages = [MagicMock(content=[MagicMock(text=r)]) for r in responses]
    client.messages.create.side_effect = messages
    return client


@pytest.mark.asyncio
async def test_expand_scenes_no_api_key():
    """Without API key, expand_scenes returns None gracefully."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = ""
    with patch("app.services.scene_expander.get_settings", return_value=mock_settings):
        result = await expand_scenes(
            task_id="t-1",
            outline=_make_outline(2),
            cast_profiles={"Alex": "Brave explorer"},
        )
    assert result is None


@pytest.mark.asyncio
async def test_expand_scenes_success():
    """All scenes expanded and assembled into full_script."""
    outline = _make_outline(3)
    responses = [_raw_scene(i, "Alex") for i in range(1, 4)]

    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"
    mock_client = _make_mock_client(responses)

    with patch("app.services.scene_expander.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = await expand_scenes(
            task_id="t-1",
            outline=outline,
            cast_profiles={"Alex": "Brave explorer"},
        )

    assert result is not None
    assert "scenes" in result
    assert len(result["scenes"]) == 3
    assert mock_client.messages.create.call_count == 3


@pytest.mark.asyncio
async def test_expand_scenes_llm_error_returns_none():
    """LLM failure on any scene returns None without raising."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("timeout")

    with patch("app.services.scene_expander.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = await expand_scenes(
            task_id="t-1",
            outline=_make_outline(1),
            cast_profiles={"Alex": None},
        )
    assert result is None


@pytest.mark.asyncio
async def test_expand_scenes_bad_json_returns_none():
    """Malformed LLM output for any scene returns None."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"
    mock_client = _make_mock_client(['{"bad": "schema"}'])

    with patch("app.services.scene_expander.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = await expand_scenes(
            task_id="t-1",
            outline=_make_outline(1),
            cast_profiles={"Alex": None},
        )
    assert result is None


@pytest.mark.asyncio
async def test_expand_scenes_unlisted_character_returns_none():
    """Dialogue with an unlisted character causes expand_scenes to return None."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"
    mock_client = _make_mock_client([_raw_scene(1, "Ghost")])

    with patch("app.services.scene_expander.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = await expand_scenes(
            task_id="t-1",
            outline=_make_outline(1),
            cast_profiles={"Alex": None},  # Ghost not in cast
        )
    assert result is None


@pytest.mark.asyncio
async def test_expand_scenes_empty_outline_returns_none():
    """An outline with no scenes returns None immediately."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"

    with patch("app.services.scene_expander.get_settings", return_value=mock_settings):
        result = await expand_scenes(
            task_id="t-1",
            outline={"acts": []},
            cast_profiles={},
        )
    assert result is None
