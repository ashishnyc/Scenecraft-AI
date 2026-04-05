"""Tests for story bible integration (SA-23)."""
import json
import pytest
from unittest.mock import MagicMock, patch

from app.services.story_bible import (
    blank_bible,
    extract_episode_events,
    merge_bible,
)
from app.services.outline_generator import _build_prompt


# ── Unit: blank_bible ─────────────────────────────────────────────────────────

def test_blank_bible_has_required_keys():
    bible = blank_bible()
    assert "character_states" in bible
    assert "plot_threads" in bible
    assert "world_building" in bible
    assert "previous_episodes" in bible


def test_blank_bible_returns_independent_copies():
    b1 = blank_bible()
    b2 = blank_bible()
    b1["world_building"].append("rule")
    assert b2["world_building"] == []


# ── Unit: merge_bible ─────────────────────────────────────────────────────────

class TestMergeBible:
    def _new_events(self, ep: int = 1) -> dict:
        return {
            "character_states": {"Alex": {"status": "alive", "last_seen": "Manor", "notes": "suspicious"}},
            "resolved_thread_ids": [],
            "new_threads": [{"description": "Hidden treasure", "introduced_ep": ep}],
            "new_world_building": ["The manor has a secret basement."],
            "episode_summary": {
                "episode_number": ep,
                "summary": "Alex discovers the manor.",
                "key_events": ["Arrived at manor", "Found locked door"],
            },
        }

    def test_merge_onto_blank_bible(self):
        result = merge_bible(None, self._new_events(1))
        assert result["character_states"]["Alex"]["status"] == "alive"
        assert len(result["plot_threads"]) == 1
        assert result["plot_threads"][0]["status"] == "open"
        assert len(result["world_building"]) == 1
        assert len(result["previous_episodes"]) == 1

    def test_merge_accumulates_episodes(self):
        bible = merge_bible(None, self._new_events(1))
        bible = merge_bible(bible, self._new_events(2))
        assert len(bible["previous_episodes"]) == 2
        assert len(bible["plot_threads"]) == 2

    def test_resolved_thread_marked(self):
        bible = merge_bible(None, self._new_events(1))
        thread_id = bible["plot_threads"][0]["id"]
        events2 = {
            "character_states": {},
            "resolved_thread_ids": [thread_id],
            "new_threads": [],
            "new_world_building": [],
            "episode_summary": {"episode_number": 2, "summary": "Resolved.", "key_events": []},
        }
        bible = merge_bible(bible, events2)
        assert bible["plot_threads"][0]["status"] == "resolved"
        assert bible["plot_threads"][0]["resolved_ep"] == 2

    def test_world_building_no_duplicates(self):
        bible = merge_bible(None, self._new_events(1))
        # Merge same rule again
        bible = merge_bible(bible, {
            "character_states": {},
            "resolved_thread_ids": [],
            "new_threads": [],
            "new_world_building": ["The manor has a secret basement."],
            "episode_summary": {"episode_number": 2, "summary": "x", "key_events": []},
        })
        assert bible["world_building"].count("The manor has a secret basement.") == 1

    def test_character_state_updated(self):
        bible = merge_bible(None, self._new_events(1))
        events2 = {
            "character_states": {"Alex": {"status": "missing", "last_seen": "Basement", "notes": "vanished"}},
            "resolved_thread_ids": [],
            "new_threads": [],
            "new_world_building": [],
            "episode_summary": {"episode_number": 2, "summary": "Alex missing.", "key_events": []},
        }
        bible = merge_bible(bible, events2)
        assert bible["character_states"]["Alex"]["status"] == "missing"


# ── Unit: outline prompt includes story bible ─────────────────────────────────

def test_build_prompt_no_bible():
    prompt = _build_prompt("brief", None, {}, ["Alex"])
    assert "story bible" not in prompt.lower()


def test_build_prompt_with_bible():
    bible = blank_bible()
    bible["world_building"] = ["Magic is real"]
    bible["previous_episodes"] = [{"episode_number": 1, "summary": "Intro episode", "key_events": []}]
    prompt = _build_prompt("brief", None, {}, ["Alex"], story_bible=bible)
    assert "story bible" in prompt.lower()
    assert "Magic is real" in prompt


def test_build_prompt_empty_bible_still_included():
    bible = blank_bible()
    prompt = _build_prompt("brief", None, {}, [], story_bible=bible)
    assert "story bible" in prompt.lower()


# ── Integration: extract_episode_events ──────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_no_api_key():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = ""
    with patch("app.services.story_bible.get_settings", return_value=mock_settings):
        result = await extract_episode_events(
            task_id="t-1",
            full_script={"scenes": []},
            existing_bible=None,
            episode_number=1,
        )
    assert result is None


@pytest.mark.asyncio
async def test_extract_valid_response():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"

    events = {
        "character_states": {"Alex": {"status": "alive", "last_seen": "Manor", "notes": ""}},
        "resolved_thread_ids": [],
        "new_threads": [{"description": "New threat", "introduced_ep": 1}],
        "new_world_building": ["Ghosts are real."],
        "episode_summary": {"episode_number": 1, "summary": "First ep.", "key_events": ["Arrived"]},
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=json.dumps(events))]
    )

    with patch("app.services.story_bible.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = await extract_episode_events(
            task_id="t-1",
            full_script={"scenes": [{"scene_number": 1, "narration": "x"}]},
            existing_bible=None,
            episode_number=1,
        )

    assert result is not None
    assert "character_states" in result
    assert result["episode_summary"]["episode_number"] == 1


@pytest.mark.asyncio
async def test_extract_llm_error_returns_none():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API down")

    with patch("app.services.story_bible.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = await extract_episode_events(
            task_id="t-1",
            full_script={"scenes": []},
            existing_bible=None,
            episode_number=1,
        )
    assert result is None
