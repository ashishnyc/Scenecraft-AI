"""Audio assembly (Audio Pipeline — SA-26 + SA-29).

Uses FFmpeg to:
  1. Concatenate all audio stems in line order
  2. Insert 0.5s silence gaps between scenes
  3. Add ID3 chapter markers (one per scene)
  4. Normalise to -14 LUFS

Uploads the assembled preview.mp3 to S3 and returns a stem registry
(SA-29) mapping each stem to its metadata.

S3 path for preview: tasks/{task_id}/audio/preview.mp3
"""
from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import tempfile
from typing import Any

from app.core.config import get_settings
from app.db.s3 import get_s3_client

logger = logging.getLogger(__name__)

_SCENE_GAP_MS = 500  # 0.5s silence between scenes
_TARGET_LUFS = -14


# ── Timing helpers ────────────────────────────────────────────────────────────

def compute_chapter_timestamps(
    routing_manifest: list[dict],
    stem_durations_ms: dict[int, int],
) -> dict[int, int]:
    """
    Return {scene_number: start_ms} chapter map.

    *stem_durations_ms* maps line_index → duration in milliseconds.
    Scenes are separated by _SCENE_GAP_MS of silence.
    """
    chapters: dict[int, int] = {}
    cursor_ms = 0
    current_scene: int | None = None

    for entry in routing_manifest:
        scene = entry["scene_number"]
        idx = entry["line_index"]

        if scene != current_scene:
            if current_scene is not None:
                cursor_ms += _SCENE_GAP_MS
            chapters[scene] = cursor_ms
            current_scene = scene

        cursor_ms += stem_durations_ms.get(idx, 0)

    return chapters


def _get_audio_duration_ms(path: str) -> int:
    """Return duration in milliseconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", path,
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    return int(float(data["format"]["duration"]) * 1000)


def _download_from_s3(bucket: str, key: str, dest: str) -> None:
    get_s3_client().download_file(bucket, key, dest)


def _upload_to_s3(src: str, bucket: str, key: str) -> None:
    get_s3_client().upload_file(
        src, bucket, key, ExtraArgs={"ContentType": "audio/mpeg"}
    )


def _s3_key_from_url(url: str) -> str:
    """Extract bucket/key from s3://bucket/key URL."""
    return url.split("//", 1)[1].split("/", 1)[1]


# ── Assembly ──────────────────────────────────────────────────────────────────

def assemble_audio_sync(
    task_id: str,
    routing_manifest: list[dict],
    stem_s3_urls: dict[int, str],
) -> tuple[str, dict[str, Any]] | None:
    """
    Synchronous FFmpeg assembly.  Called from the async wrapper below.

    Returns ``(preview_s3_url, stem_registry)`` or ``None`` on failure.
    """
    settings = get_settings()
    bucket = settings.S3_BUCKET

    if not stem_s3_urls:
        logger.error("No stems available for assembly (task %s)", task_id)
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        # Download all stems
        local_stems: dict[int, str] = {}
        for idx, url in stem_s3_urls.items():
            key = _s3_key_from_url(url)
            local_path = os.path.join(tmpdir, f"{idx:04d}.mp3")
            try:
                _download_from_s3(bucket, key, local_path)
                local_stems[idx] = local_path
            except Exception as exc:
                logger.error("Failed to download stem %d: %s", idx, exc)

        if not local_stems:
            return None

        # Measure durations
        stem_durations_ms: dict[int, int] = {}
        for idx, path in local_stems.items():
            try:
                stem_durations_ms[idx] = _get_audio_duration_ms(path)
            except Exception:
                stem_durations_ms[idx] = 0

        # Compute chapter timestamps
        chapters = compute_chapter_timestamps(routing_manifest, stem_durations_ms)

        # Build FFmpeg concat list with silence gaps between scenes
        concat_path = os.path.join(tmpdir, "concat.txt")
        silence_path = os.path.join(tmpdir, "silence.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             f"-i", f"anullsrc=r=44100:cl=mono:d={_SCENE_GAP_MS / 1000}",
             silence_path],
            capture_output=True, check=True,
        )

        current_scene: int | None = None
        with open(concat_path, "w") as f:
            for entry in routing_manifest:
                idx = entry["line_index"]
                if idx not in local_stems:
                    continue
                if entry["scene_number"] != current_scene:
                    if current_scene is not None:
                        f.write(f"file '{silence_path}'\n")
                    current_scene = entry["scene_number"]
                f.write(f"file '{local_stems[idx]}'\n")

        raw_path = os.path.join(tmpdir, "raw.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_path, "-c", "copy", raw_path],
            capture_output=True, check=True,
        )

        # Normalise to -14 LUFS
        normalised_path = os.path.join(tmpdir, "preview.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-i", raw_path,
             "-af", f"loudnorm=I={_TARGET_LUFS}:TP=-1.5:LRA=11",
             normalised_path],
            capture_output=True, check=True,
        )

        # Upload preview
        preview_key = f"tasks/{task_id}/audio/preview.mp3"
        _upload_to_s3(normalised_path, bucket, preview_key)
        preview_url = f"s3://{bucket}/{preview_key}"

        # Build stem registry (SA-29)
        stems_registry = [
            {
                "line_index": entry["line_index"],
                "s3_url": stem_s3_urls.get(entry["line_index"], ""),
                "scene_number": entry["scene_number"],
                "character_name": entry["character_name"],
                "duration_ms": stem_durations_ms.get(entry["line_index"], 0),
                "approved": False,
            }
            for entry in routing_manifest
            if entry["line_index"] in stem_s3_urls
        ]
        stem_registry = {
            "stems": stems_registry,
            "preview_url": preview_url,
            "chapter_timestamps": chapters,
            "approved": False,
        }

    logger.info("Audio assembled for task %s: %d stems, preview at %s", task_id, len(stems_registry), preview_url)
    return preview_url, stem_registry


async def assemble_audio(
    task_id: str,
    routing_manifest: list[dict],
    stem_s3_urls: dict[int, str],
) -> tuple[str, dict[str, Any]] | None:
    """Async wrapper around the synchronous FFmpeg assembly."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, assemble_audio_sync, task_id, routing_manifest, stem_s3_urls
    )
