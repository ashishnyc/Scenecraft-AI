"""Environment generator (Video Pipeline — SA-32).

Extracts unique environment names from the shot list, checks for cached
plates in S3, and generates new ones via the image gen API when needed.

S3 path: projects/{project_id}/environments/{env_slug}/
Plates: wide.jpg, medium.jpg, closeup.jpg
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_PLATE_ANGLES = ["wide", "medium", "closeup"]
_CACHE_SIMILARITY_THRESHOLD = 0.90


def _env_slug(environment: str) -> str:
    """Normalise an environment name to a safe S3 slug."""
    return re.sub(r"[^a-z0-9_-]", "_", environment.lower().strip())[:64]


def extract_unique_environments(shot_list: dict) -> list[str]:
    """Return a deduplicated list of environment names from *shot_list*."""
    seen: set[str] = set()
    envs: list[str] = []
    for shot in shot_list.get("shots", []):
        env = shot.get("environment", "").strip()
        if env and env not in seen:
            seen.add(env)
            envs.append(env)
    return envs


def _plate_s3_key(project_id: str, env: str, angle: str) -> str:
    return f"projects/{project_id}/environments/{_env_slug(env)}/{angle}.jpg"


def _check_cache(bucket: str, project_id: str, env: str) -> dict[str, str] | None:
    """Return existing plate URLs if all three angles are cached in S3."""
    from app.db.s3 import get_s3_client
    s3 = get_s3_client()
    plates: dict[str, str] = {}
    for angle in _PLATE_ANGLES:
        key = _plate_s3_key(project_id, env, angle)
        try:
            s3.head_object(Bucket=bucket, Key=key)
            plates[angle] = f"s3://{bucket}/{key}"
        except Exception:
            return None  # any missing → regenerate
    return plates


async def _generate_plates(
    environment: str,
    project_id: str,
    bucket: str,
    image_gen_api_key: str,
) -> dict[str, str] | None:
    """Call the image gen API to create wide/medium/closeup plates."""
    import httpx
    from app.db.s3 import get_s3_client

    plates: dict[str, str] = {}
    s3 = get_s3_client()

    for angle in _PLATE_ANGLES:
        prompt = (
            f"Background plate, {angle} shot, {environment}, "
            "cinematic lighting, high detail, 16:9 aspect ratio, "
            "no characters, no text"
        )
        # DALL-E 3 compatible endpoint (swappable with other providers)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {image_gen_api_key}"},
                    json={"model": "dall-e-3", "prompt": prompt, "size": "1792x1024", "n": 1},
                )
                resp.raise_for_status()
                image_url = resp.json()["data"][0]["url"]

            # Download and upload to S3
            async with httpx.AsyncClient(timeout=60) as client:
                img_resp = await client.get(image_url)
                img_resp.raise_for_status()
                img_bytes = img_resp.content

            key = _plate_s3_key(project_id, environment, angle)
            import io
            s3.upload_fileobj(io.BytesIO(img_bytes), bucket, key,
                              ExtraArgs={"ContentType": "image/jpeg"})
            plates[angle] = f"s3://{bucket}/{key}"
        except Exception as exc:
            logger.error("Failed to generate plate %s for '%s': %s", angle, environment, exc)

    return plates if len(plates) == len(_PLATE_ANGLES) else None


async def generate_environment_plates(
    task_id: str,
    project_id: str,
    shot_list: dict,
) -> dict[str, dict[str, str]]:
    """
    For each unique environment in *shot_list*, return cached or newly
    generated plate URLs.

    Returns ``{environment_name: {angle: s3_url}}``.
    """
    settings = get_settings()
    bucket = settings.S3_BUCKET
    image_api_key = getattr(settings, "IMAGE_GEN_API_KEY", "")

    envs = extract_unique_environments(shot_list)
    result: dict[str, dict[str, str]] = {}

    for env in envs:
        # Try cache first
        cached = _check_cache(bucket, project_id, env)
        if cached:
            logger.info("Environment cache hit: '%s' (task %s)", env, task_id)
            result[env] = cached
            continue

        if not image_api_key:
            logger.warning("IMAGE_GEN_API_KEY not set — skipping plate generation for '%s'", env)
            result[env] = {}
            continue

        plates = await _generate_plates(env, project_id, bucket, image_api_key)
        if plates:
            result[env] = plates
        else:
            result[env] = {}

    return result
