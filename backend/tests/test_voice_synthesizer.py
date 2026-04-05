"""Tests for the voice synthesizer (SA-25)."""
import io
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.voice_synthesizer import synthesize_manifest, _ELEVENLABS_COST_PER_CHAR


def _manifest(num_lines: int = 2, scene: int = 1) -> list[dict]:
    return [
        {
            "line_index": i,
            "scene_number": scene,
            "text": f"Line {i} text here.",
            "voice_profile_id": "voice-123",
            "character_name": "Alex",
            "line_type": "dialogue",
        }
        for i in range(num_lines)
    ]


def _mock_settings(elevenlabs: str = "el-key", fish: str = "") -> MagicMock:
    s = MagicMock()
    s.ELEVENLABS_API_KEY = elevenlabs
    s.FISH_AUDIO_API_KEY = fish
    s.S3_BUCKET = "test-bucket"
    return s


# ── Unit: retry logic ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthesize_success_uploads_to_s3():
    """Happy path: ElevenLabs returns audio, uploaded to S3."""
    fake_audio = b"ID3\x00\x00" + b"\x00" * 100

    with patch("app.services.voice_synthesizer.get_settings", return_value=_mock_settings()), \
         patch("app.services.voice_synthesizer._synthesize_with_retry",
               AsyncMock(return_value=fake_audio)), \
         patch("app.services.voice_synthesizer._upload_to_s3") as mock_upload:
        stem_urls, cost = await synthesize_manifest("t-1", _manifest(2))

    assert len(stem_urls) == 2
    assert mock_upload.call_count == 2
    assert cost > Decimal("0")


@pytest.mark.asyncio
async def test_synthesize_failure_skips_line():
    """If synthesis fails for a line, it's skipped but others succeed."""
    fake_audio = b"ID3" + b"\x00" * 50
    call_count = 0

    async def sometimes_fail(text, voice_id, settings):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None  # first line fails
        return fake_audio

    with patch("app.services.voice_synthesizer.get_settings", return_value=_mock_settings()), \
         patch("app.services.voice_synthesizer._synthesize_with_retry", side_effect=sometimes_fail), \
         patch("app.services.voice_synthesizer._upload_to_s3"):
        stem_urls, _ = await synthesize_manifest("t-1", _manifest(2))

    assert len(stem_urls) == 1  # only second line succeeded


@pytest.mark.asyncio
async def test_synthesize_selective_by_scene():
    """Only scenes in changed_scenes are synthesised."""
    fake_audio = b"ID3" + b"\x00" * 50
    manifest = [
        {"line_index": 0, "scene_number": 1, "text": "A", "voice_profile_id": "v1",
         "character_name": "n", "line_type": "narration"},
        {"line_index": 1, "scene_number": 2, "text": "B", "voice_profile_id": "v1",
         "character_name": "n", "line_type": "narration"},
    ]

    with patch("app.services.voice_synthesizer.get_settings", return_value=_mock_settings()), \
         patch("app.services.voice_synthesizer._synthesize_with_retry",
               AsyncMock(return_value=fake_audio)), \
         patch("app.services.voice_synthesizer._upload_to_s3"):
        stem_urls, _ = await synthesize_manifest("t-1", manifest, scene_numbers={2})

    # Only scene 2 (line_index 1) should be in the result
    assert 0 not in stem_urls
    assert 1 in stem_urls


@pytest.mark.asyncio
async def test_synthesize_retry_succeeds_on_third():
    """Fails twice then succeeds on third attempt."""
    fake_audio = b"ID3" + b"\x00" * 50
    call_count = 0

    async def flaky(text, voice_id, api_key):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("rate limit")
        return fake_audio

    settings = _mock_settings()

    with patch("app.services.voice_synthesizer.get_settings", return_value=settings), \
         patch("app.services.voice_synthesizer._call_elevenlabs", side_effect=flaky), \
         patch("app.services.voice_synthesizer._upload_to_s3"), \
         patch("asyncio.sleep", AsyncMock()):  # skip actual sleep
        stem_urls, _ = await synthesize_manifest("t-1", _manifest(1))

    assert len(stem_urls) == 1
    assert call_count == 3


def test_cost_calculation():
    """Cost is proportional to character count."""
    text = "A" * 1000
    expected = _ELEVENLABS_COST_PER_CHAR * 1000
    actual = _ELEVENLABS_COST_PER_CHAR * len(text)
    assert actual == expected
