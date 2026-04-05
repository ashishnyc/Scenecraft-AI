"""Tests for the audio assembler (SA-26 + SA-29)."""
import json
import pytest
from unittest.mock import MagicMock, patch, call

from app.services.audio_assembler import compute_chapter_timestamps, _SCENE_GAP_MS


def _manifest(scene_map: dict[int, list[int]]) -> list[dict]:
    """Build manifest from {scene_number: [line_indices]}."""
    entries = []
    for scene, indices in scene_map.items():
        for idx in indices:
            entries.append({
                "line_index": idx,
                "scene_number": scene,
                "text": f"Line {idx}",
                "voice_profile_id": "v1",
                "character_name": "narrator",
                "line_type": "narration",
            })
    return entries


# ── Unit: chapter timestamp calculation ──────────────────────────────────────

def test_single_scene_starts_at_zero():
    manifest = _manifest({1: [0, 1, 2]})
    durations = {0: 1000, 1: 1500, 2: 2000}
    chapters = compute_chapter_timestamps(manifest, durations)
    assert chapters[1] == 0


def test_two_scenes_gap_added():
    manifest = _manifest({1: [0], 2: [1]})
    durations = {0: 2000, 1: 3000}
    chapters = compute_chapter_timestamps(manifest, durations)
    assert chapters[1] == 0
    assert chapters[2] == 2000 + _SCENE_GAP_MS


def test_three_scenes_cumulative():
    manifest = _manifest({1: [0, 1], 2: [2], 3: [3]})
    durations = {0: 1000, 1: 1000, 2: 2000, 3: 500}
    chapters = compute_chapter_timestamps(manifest, durations)
    assert chapters[1] == 0
    assert chapters[2] == 2000 + _SCENE_GAP_MS
    assert chapters[3] == 2000 + _SCENE_GAP_MS + 2000 + _SCENE_GAP_MS


def test_missing_duration_treated_as_zero():
    manifest = _manifest({1: [0]})
    chapters = compute_chapter_timestamps(manifest, {})  # no durations
    assert chapters[1] == 0


def test_empty_manifest_returns_empty():
    assert compute_chapter_timestamps([], {}) == {}


# ── Integration: assemble_audio_sync with mocked FFmpeg + S3 ─────────────────

def _make_settings():
    s = MagicMock()
    s.S3_BUCKET = "test-bucket"
    return s


def _stem_urls(indices: list[int]) -> dict[int, str]:
    return {i: f"s3://test-bucket/tasks/t1/audio/stems/{i:04d}.mp3" for i in indices}


def test_assemble_empty_stems_returns_none():
    from app.services.audio_assembler import assemble_audio_sync
    with patch("app.services.audio_assembler.get_settings", return_value=_make_settings()):
        result = assemble_audio_sync("t1", [], {})
    assert result is None


def test_assemble_calls_ffmpeg_and_uploads():
    from app.services.audio_assembler import assemble_audio_sync

    manifest = _manifest({1: [0, 1], 2: [2]})
    stems = _stem_urls([0, 1, 2])

    mock_proc = MagicMock(returncode=0)

    with patch("app.services.audio_assembler.get_settings", return_value=_make_settings()), \
         patch("app.services.audio_assembler._download_from_s3"), \
         patch("app.services.audio_assembler._get_audio_duration_ms", return_value=1000), \
         patch("subprocess.run", return_value=mock_proc) as mock_run, \
         patch("app.services.audio_assembler._upload_to_s3") as mock_upload:
        result = assemble_audio_sync("t1", manifest, stems)

    assert result is not None
    preview_url, registry = result
    assert preview_url.endswith("preview.mp3")
    assert "stems" in registry
    assert len(registry["stems"]) == 3
    assert "chapter_timestamps" in registry
    assert registry["approved"] is False
    assert mock_upload.called


def test_assemble_stem_registry_structure():
    from app.services.audio_assembler import assemble_audio_sync

    manifest = _manifest({1: [0]})
    stems = _stem_urls([0])

    with patch("app.services.audio_assembler.get_settings", return_value=_make_settings()), \
         patch("app.services.audio_assembler._download_from_s3"), \
         patch("app.services.audio_assembler._get_audio_duration_ms", return_value=2500), \
         patch("subprocess.run", return_value=MagicMock(returncode=0)), \
         patch("app.services.audio_assembler._upload_to_s3"):
        result = assemble_audio_sync("t1", manifest, stems)

    assert result is not None
    _, registry = result
    stem = registry["stems"][0]
    assert stem["line_index"] == 0
    assert stem["scene_number"] == 1
    assert stem["duration_ms"] == 2500
    assert stem["approved"] is False
    assert stem["s3_url"] == stems[0]
