"""Thumbnail generator (SA-39).

Generates 5 AI thumbnail options using DALL-E (IMAGE_GEN_API_KEY) based on
the task's title, outline, and selected shots. Falls back to None if the API
key is absent.

S3 path: tasks/{task_id}/thumbnails/{index}.jpg
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Any

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.task import Task
from app.db.s3 import get_s3_client
from sqlalchemy import select

logger = logging.getLogger(__name__)

_NUM_OPTIONS = 5
_THUMBNAIL_SIZE = "1792x1024"  # DALL-E 3 landscape


async def generate_thumbnail_options(task_id: str) -> list[dict[str, str]] | None:
    """
    Generate *_NUM_OPTIONS* thumbnail images for the task.

    Returns list of ``{"index": i, "s3_url": "s3://...", "prompt": "..."}``
    or None on failure.
    """
    settings = get_settings()
    if not settings.IMAGE_GEN_API_KEY:
        logger.warning("IMAGE_GEN_API_KEY not set — thumbnail generation skipped")
        return None

    try:
        import openai
        client = openai.OpenAI(api_key=settings.IMAGE_GEN_API_KEY)
    except ImportError:
        logger.error("openai package not installed")
        return None

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            return None

        script = row.script or {}
        outline = script.get("outline", {})
        title = row.title or "Untitled"
        logline = outline.get("logline", "")
        genre = outline.get("genre", "drama")

        base_prompt = (
            f"YouTube thumbnail for a {genre} video titled '{title}'. "
            f"Logline: {logline}. "
            "Cinematic composition, 16:9 aspect ratio, high contrast, bold text space at bottom. "
            "Photorealistic."
        )

    s3 = get_s3_client()
    bucket = settings.S3_BUCKET
    options: list[dict[str, str]] = []

    style_modifiers = [
        "dramatic close-up of the protagonist",
        "wide establishing shot of the main location",
        "action moment with motion blur",
        "emotional character confrontation scene",
        "mysterious atmosphere with symbolic imagery",
    ]

    for i, modifier in enumerate(style_modifiers[:_NUM_OPTIONS]):
        prompt = f"{base_prompt} Style: {modifier}."
        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size=_THUMBNAIL_SIZE,
                response_format="b64_json",
            )
            img_b64 = response.data[0].b64_json
            img_bytes = base64.b64decode(img_b64)
            key = f"tasks/{task_id}/thumbnails/{i}.jpg"
            s3.put_object(
                Bucket=bucket, Key=key, Body=img_bytes,
                ContentType="image/jpeg",
            )
            s3_url = f"s3://{bucket}/{key}"
            signed_url = s3.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600
            )
            options.append({"index": str(i), "s3_url": s3_url, "signed_url": signed_url, "prompt": prompt})
            logger.info("Thumbnail %d generated for task %s", i, task_id)
        except Exception as exc:
            logger.warning("Thumbnail %d generation failed for task %s: %s", i, task_id, exc)

    if not options:
        return None

    # Persist options list in task.script
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if row:
            sc = dict(row.script or {})
            sc["thumbnail_options"] = options
            row.script = sc
            db.add(row)
            await db.commit()
        break

    return options
