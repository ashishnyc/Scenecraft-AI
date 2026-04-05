"""Voice synthesis integration (Audio Pipeline — SA-25).

Primary: ElevenLabs API.  Fallback: Fish Audio API.
Each routing manifest entry becomes one MP3 stem uploaded to S3.

S3 path: tasks/{task_id}/audio/stems/{line_index:04d}.mp3
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings
from app.db.s3 import get_s3_client

logger = logging.getLogger(__name__)

# ElevenLabs charges approximately $0.30 per 1000 characters (Starter plan)
_ELEVENLABS_COST_PER_CHAR = Decimal("0.0003")
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0  # seconds


def _stem_s3_key(task_id: str, line_index: int) -> str:
    return f"tasks/{task_id}/audio/stems/{line_index:04d}.mp3"


def _stem_s3_url(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


async def _call_elevenlabs(text: str, voice_id: str, api_key: str) -> bytes:
    """Call ElevenLabs TTS API and return raw MP3 bytes."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.content


async def _call_fish_audio(text: str, voice_id: str, api_key: str) -> bytes:
    """Call Fish Audio TTS API and return raw MP3 bytes."""
    url = "https://api.fish.audio/v1/tts"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"text": text, "reference_id": voice_id, "format": "mp3"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.content


async def _synthesize_with_retry(
    text: str,
    voice_id: str,
    settings: Any,
) -> bytes | None:
    """Try ElevenLabs then Fish Audio, each with exponential backoff."""
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        if attempt:
            await asyncio.sleep(_BACKOFF_BASE ** attempt)

        # Primary: ElevenLabs
        if settings.ELEVENLABS_API_KEY:
            try:
                return await _call_elevenlabs(text, voice_id, settings.ELEVENLABS_API_KEY)
            except Exception as exc:
                last_exc = exc
                logger.warning("ElevenLabs attempt %d failed: %s", attempt + 1, exc)

        # Fallback: Fish Audio
        if settings.FISH_AUDIO_API_KEY:
            try:
                return await _call_fish_audio(text, voice_id, settings.FISH_AUDIO_API_KEY)
            except Exception as exc:
                last_exc = exc
                logger.warning("Fish Audio attempt %d failed: %s", attempt + 1, exc)

    logger.error("All synthesis attempts failed: %s", last_exc)
    return None


def _upload_to_s3(audio_bytes: bytes, bucket: str, key: str) -> None:
    client = get_s3_client()
    client.upload_fileobj(
        io.BytesIO(audio_bytes),
        bucket,
        key,
        ExtraArgs={"ContentType": "audio/mpeg"},
    )


async def synthesize_manifest(
    task_id: str,
    routing_manifest: list[dict],
    scene_numbers: set[int] | None = None,
) -> tuple[dict[int, str], Decimal]:
    """
    Synthesize all entries in *routing_manifest* and upload stems to S3.

    If *scene_numbers* is given, only synthesize entries for those scenes
    (selective re-generation — SA-28).

    Returns ``(stem_urls, total_cost)`` where:
      - stem_urls maps line_index → S3 URL
      - total_cost is the accumulated ElevenLabs character cost
    """
    settings = get_settings()
    bucket = settings.S3_BUCKET

    stem_urls: dict[int, str] = {}
    total_cost = Decimal("0")

    entries_to_process = [
        e for e in routing_manifest
        if scene_numbers is None or e["scene_number"] in scene_numbers
    ]

    for entry in entries_to_process:
        line_index = entry["line_index"]
        text = entry["text"]
        voice_id = entry["voice_profile_id"]

        audio = await _synthesize_with_retry(text, voice_id, settings)
        if audio is None:
            logger.error("Synthesis failed for line %d (task %s)", line_index, task_id)
            continue

        key = _stem_s3_key(task_id, line_index)
        try:
            _upload_to_s3(audio, bucket, key)
        except Exception as exc:
            logger.error("S3 upload failed for line %d (task %s): %s", line_index, task_id, exc)
            continue

        stem_urls[line_index] = _stem_s3_url(bucket, key)
        total_cost += _ELEVENLABS_COST_PER_CHAR * len(text)

    return stem_urls, total_cost
