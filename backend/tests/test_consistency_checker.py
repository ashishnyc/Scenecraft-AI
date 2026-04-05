"""Tests for the consistency checker (script pipeline stage 3)."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.consistency_checker import (
    ConsistencyFlag,
    ConsistencyReport,
    _parse_report,
    check_consistency,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_full_script(num_scenes: int = 3) -> dict:
    return {
        "scenes": [
            {
                "scene_number": i,
                "narration": f"Scene {i} narration.",
                "dialogue": [],
                "visual_direction": "Wide shot.",
                "estimated_duration_seconds": 60,
            }
            for i in range(1, num_scenes + 1)
        ]
    }


def _make_outline(num_scenes: int = 3) -> dict:
    return {
        "acts": [
            {
                "act_number": 1,
                "title": "Act 1",
                "scenes": [
                    {
                        "scene_number": i,
                        "location": "Office",
                        "time_of_day": "Day",
                        "summary": f"Summary {i}",
                        "characters_present": [],
                    }
                    for i in range(1, num_scenes + 1)
                ],
            }
        ]
    }


def _report_raw(flags: list[dict]) -> str:
    return json.dumps({"flags": flags})


# ── Unit: schema ──────────────────────────────────────────────────────────────

class TestConsistencyReport:
    def test_no_flags_has_no_blockers(self):
        report = ConsistencyReport(flags=[])
        assert report.has_blockers is False  # type: ignore[attr-defined]

    def test_warning_only_has_no_blockers(self):
        report = ConsistencyReport(flags=[
            ConsistencyFlag(scene_number=1, issue_type="pacing_issue",
                            description="Too slow", severity="warning")
        ])
        assert report.has_blockers is False  # type: ignore[attr-defined]

    def test_blocker_sets_has_blockers(self):
        report = ConsistencyReport(flags=[
            ConsistencyFlag(scene_number=2, issue_type="plot_hole",
                            description="Character vanishes", severity="blocker")
        ])
        assert report.has_blockers is True  # type: ignore[attr-defined]

    def test_blocker_scene_numbers(self):
        report = ConsistencyReport(flags=[
            ConsistencyFlag(scene_number=2, issue_type="plot_hole",
                            description="X", severity="blocker"),
            ConsistencyFlag(scene_number=5, issue_type="character_inconsistency",
                            description="Y", severity="blocker"),
            ConsistencyFlag(scene_number=3, issue_type="pacing_issue",
                            description="Z", severity="warning"),
        ])
        assert sorted(report.blocker_scene_numbers) == [2, 5]


class TestParseReport:
    def test_empty_flags(self):
        report = _parse_report(_report_raw([]))
        assert report.flags == []

    def test_valid_flag(self):
        raw = _report_raw([{
            "scene_number": 3,
            "issue_type": "plot_hole",
            "description": "Missing motive",
            "severity": "blocker",
        }])
        report = _parse_report(raw)
        assert len(report.flags) == 1
        assert report.flags[0].severity == "blocker"

    def test_markdown_fences_stripped(self):
        inner = _report_raw([])
        raw = f"```json\n{inner}\n```"
        report = _parse_report(raw)
        assert report.flags == []

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            _parse_report("not json")


# ── Integration: check_consistency ───────────────────────────────────────────

def _mock_client(raw_response: str) -> MagicMock:
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=raw_response)]
    client.messages.create.return_value = msg
    return client


@pytest.mark.asyncio
async def test_check_consistency_no_api_key():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = ""
    with patch("app.services.consistency_checker.get_settings", return_value=mock_settings):
        result = await check_consistency(
            task_id="t-1",
            full_script=_make_full_script(),
            style_guide={},
            cast_profiles={},
            outline=_make_outline(),
        )
    assert result is None


@pytest.mark.asyncio
async def test_check_consistency_no_flags():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"
    client = _mock_client(_report_raw([]))

    with patch("app.services.consistency_checker.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=client):
        result = await check_consistency(
            task_id="t-1",
            full_script=_make_full_script(),
            style_guide={},
            cast_profiles={},
            outline=_make_outline(),
        )

    assert result is not None
    assert result["flags"] == []


@pytest.mark.asyncio
async def test_check_consistency_warnings_returned():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"
    flags = [{"scene_number": 1, "issue_type": "pacing_issue",
               "description": "Slow opening", "severity": "warning"}]
    client = _mock_client(_report_raw(flags))

    with patch("app.services.consistency_checker.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=client):
        result = await check_consistency(
            task_id="t-1",
            full_script=_make_full_script(),
            style_guide={},
            cast_profiles={},
            outline=_make_outline(),
        )

    assert result is not None
    assert len(result["flags"]) == 1
    assert result["flags"][0]["severity"] == "warning"


@pytest.mark.asyncio
async def test_check_consistency_blocker_triggers_regen():
    """Blocker scenes trigger one scene re-expansion then a second check."""
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"

    blocker_flags = [{"scene_number": 2, "issue_type": "plot_hole",
                      "description": "Gap in logic", "severity": "blocker"}]
    # First call returns a blocker; second call (after regen) returns clean
    client = MagicMock()
    client.messages.create.side_effect = [
        MagicMock(content=[MagicMock(text=_report_raw(blocker_flags))]),
        MagicMock(content=[MagicMock(text=_report_raw([]))]),
    ]

    regen_script = {
        "scenes": [{"scene_number": 2, "narration": "Fixed.", "dialogue": [],
                    "visual_direction": "Close-up.", "estimated_duration_seconds": 45}]
    }
    mock_expand = AsyncMock(return_value=regen_script)

    with patch("app.services.consistency_checker.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=client), \
         patch("app.services.consistency_checker.expand_scenes", mock_expand):
        result = await check_consistency(
            task_id="t-1",
            full_script=_make_full_script(3),
            style_guide={},
            cast_profiles={},
            outline=_make_outline(3),
        )

    assert result is not None
    assert result["flags"] == []
    mock_expand.assert_called_once()


@pytest.mark.asyncio
async def test_check_consistency_llm_error_returns_none():
    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"
    client = MagicMock()
    client.messages.create.side_effect = Exception("timeout")

    with patch("app.services.consistency_checker.get_settings", return_value=mock_settings), \
         patch("anthropic.Anthropic", return_value=client):
        result = await check_consistency(
            task_id="t-1",
            full_script=_make_full_script(),
            style_guide={},
            cast_profiles={},
            outline=_make_outline(),
        )
    assert result is None
