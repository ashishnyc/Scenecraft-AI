"""Music generation service (Video Pipeline — SA-34).

Generates per-scene background music via the Suno API (primary) and
trims/loops tracks to match the exact scene duration using FFmpeg.

S3 path: tasks/{task_id}/music/{scene_number:03d}.mp3
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import subprocess
import tempfile
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings
from app.db.s3 import get_s3_client

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5
_MAX_WAIT = 5 * 60       # 5 minutes
_COST_PER_TRACK = Decimal("0.01")


def _music_s3_key(task_id: str, scene_number: int) -> str:
    return f"tasks/{task_id}/music/{scene_number:03d}.mp3"


def extract_scene_moods(shot_list: dict) -> dict[int, list[str]]:
    """Return {scene_number: [mood, ...]} from a shot list."""
    scene_moods: dict[int, set[str]] = {}
    for shot in shot_list.get("shots", []):
        sn = shot["scene_number"]
        mood = shot.get("mood", "").strip()
        if mood:
            scene_moods.setdefault(sn, set()).add(mood)
    return {sn: list(moods) for sn, moods in scene_moods.items()}


async def _generate_suno_track(prompt: str, duration_seconds: float, api_key: str) -> bytes | None:
    """Submit a Suno job and poll until audio is ready. Returns MP3 bytes."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://studio-api.suno.ai/api/generate/v2/",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "prompt": prompt,
                    "duration": int(duration_seconds),
                    "make_instrumental": True,
                },
            )
            resp.raise_for_status()
            clips = resp.json().get("clips", [])
            if not clips:
                return None
            clip_id = clips[0]["id"]
    except Exception as exc:
        logger.error("Suno submission failed: %s", exc)
        return None

    # Poll for completion
    elapsed = 0
    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < _MAX_WAIT:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
            try:
                resp = await client.get(
                    f"https://studio-api.suno.ai/api/feed/?ids={clip_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                clip = resp.json()[0]
                if clip.get("status") == "complete":
                    audio_url = clip["audio_url"]
                    dl = await client.get(audio_url)
                    dl.raise_for_status()
                    return dl.content
            except Exception as exc:
                logger.warning("Suno poll error: %s", exc)

    logger.error("Suno job %s timed out", clip_id)
    return None


def _trim_to_duration(audio_bytes: bytes, target_seconds: float) -> bytes:
    """Use FFmpeg to trim or loop an audio file to *target_seconds*."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "src.mp3")
        dst = os.path.join(tmpdir, "dst.mp3")
        with open(src, "wb") as f:
            f.write(audio_bytes)
        subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-t", str(target_seconds),
             "-af", f"afade=out:st={max(0, target_seconds - 2)}:d=2",
             dst],
            capture_output=True, check=True,
        )
        with open(dst, "rb") as f:
            return f.read()


async def generate_music(
    task_id: str,
    shot_list: dict,
    audio_stems: dict | None,
) -> tuple[dict[int, str], Decimal]:
    """
    Generate one music track per scene.

    Uses audio stem chapter timestamps to derive each scene's duration.
    Returns ``(music_urls, total_cost)`` mapping scene_number → S3 URL.
    """
    settings = get_settings()
    api_key = getattr(settings, "SUNO_API_KEY", "")
    bucket = settings.S3_BUCKET

    if not api_key:
        logger.warning("SUNO_API_KEY not set — skipping music generation for task %s", task_id)
        return {}, Decimal("0")

    scene_moods = extract_scene_moods(shot_list)
    chapter_ts: dict[int, float] = {}
    if audio_stems:
        chapter_ts = {int(k): v / 1000 for k, v in audio_stems.get("chapter_timestamps", {}).items()}

    # Compute per-scene durations from chapter timestamps
    sorted_scenes = sorted(chapter_ts.keys())
    scene_durations: dict[int, float] = {}
    for i, sn in enumerate(sorted_scenes):
        start = chapter_ts[sn]
        end = chapter_ts[sorted_scenes[i + 1]] if i + 1 < len(sorted_scenes) else start + 60
        scene_durations[sn] = max(10.0, end - start)

    music_urls: dict[int, str] = {}
    total_cost = Decimal("0")
    s3 = get_s3_client()

    for scene_number, moods in scene_moods.items():
        duration = scene_durations.get(scene_number, 30.0)
        mood_str = ", ".join(moods) or "ambient"
        prompt = f"background instrumental music, {mood_str} mood, YouTube video scoring"

        audio = await _generate_suno_track(prompt, duration, api_key)
        if not audio:
            continue

        try:
            trimmed = _trim_to_duration(audio, duration)
        except Exception as exc:
            logger.warning("FFmpeg trim failed for scene %d: %s — using original", scene_number, exc)
            trimmed = audio

        key = _music_s3_key(task_id, scene_number)
        try:
            s3.upload_fileobj(io.BytesIO(trimmed), bucket, key, ExtraArgs={"ContentType": "audio/mpeg"})
            music_urls[scene_number] = f"s3://{bucket}/{key}"
            total_cost += _COST_PER_TRACK
        except Exception as exc:
            logger.error("S3 upload failed for music scene %d: %s", scene_number, exc)

    return music_urls, total_cost
