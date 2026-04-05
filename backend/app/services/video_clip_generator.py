"""Video clip generator (Video Pipeline — SA-33).

Submits each shot to a video generation API (Kling primary), polls for
completion, and uploads the resulting MP4 to S3.

S3 path: tasks/{task_id}/clips/{shot_index:04d}.mp4
"""
from __future__ import annotations

import asyncio
import io
import logging
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings
from app.db.s3 import get_s3_client
from app.services.character_consistency import inject_character_references

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 10       # seconds between status polls
_MAX_WAIT = 20 * 60       # 20 minutes timeout per clip
_COST_PER_CLIP = Decimal("0.05")   # ~$0.05 per 5-second clip (Kling estimate)


def _clip_s3_key(task_id: str, shot_index: int) -> str:
    return f"tasks/{task_id}/clips/{shot_index:04d}.mp4"


def _build_shot_prompt(
    shot: dict,
    reference_prompts: dict[str, str],
    env_plates: dict[str, dict[str, str]],
) -> str:
    base = (
        f"{shot['action_description']}, "
        f"{shot['camera_angle']} shot, "
        f"{shot['mood']} mood, "
        f"{shot.get('environment', '')} background"
    )
    return inject_character_references(base, shot.get("characters", []), reference_prompts)


async def _submit_kling_job(
    prompt: str,
    duration: float,
    api_key: str,
) -> str | None:
    """Submit a clip generation job to Kling and return the job ID."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.klingai.com/v1/videos/text2video",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "prompt": prompt,
                    "duration": int(duration),
                    "aspect_ratio": "16:9",
                    "mode": "standard",
                },
            )
            resp.raise_for_status()
            return resp.json()["data"]["task_id"]
    except Exception as exc:
        logger.error("Kling job submission failed: %s", exc)
        return None


async def _poll_kling_job(job_id: str, api_key: str) -> str | None:
    """Poll Kling until job completes or timeout. Returns video download URL."""
    elapsed = 0
    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < _MAX_WAIT:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
            try:
                resp = await client.get(
                    f"https://api.klingai.com/v1/videos/{job_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                status = data.get("status")
                if status == "completed":
                    return data["video_url"]
                if status in ("failed", "cancelled"):
                    logger.error("Kling job %s failed with status: %s", job_id, status)
                    return None
            except Exception as exc:
                logger.warning("Kling poll error for job %s: %s", job_id, exc)

    logger.error("Kling job %s timed out after %d minutes", job_id, _MAX_WAIT // 60)
    return None


async def _generate_single_clip(
    shot: dict,
    task_id: str,
    reference_prompts: dict[str, str],
    env_plates: dict[str, dict[str, str]],
    api_key: str,
    bucket: str,
) -> str | None:
    """Generate one clip and upload to S3. Returns S3 URL or None."""
    shot_index = shot["shot_index"]
    prompt = _build_shot_prompt(shot, reference_prompts, env_plates)
    duration = shot.get("duration_seconds", 5.0)

    job_id = await _submit_kling_job(prompt, duration, api_key)
    if not job_id:
        return None

    video_url = await _poll_kling_job(job_id, api_key)
    if not video_url:
        return None

    # Download and upload to S3
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(video_url)
            resp.raise_for_status()
            video_bytes = resp.content

        key = _clip_s3_key(task_id, shot_index)
        get_s3_client().upload_fileobj(
            io.BytesIO(video_bytes), bucket, key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
        return f"s3://{bucket}/{key}"
    except Exception as exc:
        logger.error("S3 upload failed for clip %d: %s", shot_index, exc)
        return None


async def generate_clips(
    task_id: str,
    shot_list: dict,
    reference_prompts: dict[str, str],
    env_plates: dict[str, dict[str, str]],
    batch_size: int = 5,
) -> tuple[dict[int, str], Decimal]:
    """
    Generate MP4 clips for all shots in *shot_list* in parallel batches.

    Returns ``(clip_urls, total_cost)`` where clip_urls maps
    shot_index → S3 URL.
    """
    settings = get_settings()
    api_key = getattr(settings, "KLING_API_KEY", "")
    bucket = settings.S3_BUCKET

    if not api_key:
        logger.warning("KLING_API_KEY not set — skipping clip generation for task %s", task_id)
        return {}, Decimal("0")

    shots = shot_list.get("shots", [])
    clip_urls: dict[int, str] = {}
    total_cost = Decimal("0")

    # Process in batches
    for i in range(0, len(shots), batch_size):
        batch = shots[i:i + batch_size]
        results = await asyncio.gather(
            *[
                _generate_single_clip(shot, task_id, reference_prompts, env_plates, api_key, bucket)
                for shot in batch
            ],
            return_exceptions=False,
        )
        for shot, url in zip(batch, results):
            if url:
                clip_urls[shot["shot_index"]] = url
                total_cost += _COST_PER_CLIP

    logger.info("Clip generation: %d/%d succeeded for task %s", len(clip_urls), len(shots), task_id)
    return clip_urls, total_cost
