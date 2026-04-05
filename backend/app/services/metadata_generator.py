"""YouTube metadata generator (SA-40).

Uses Claude to pre-fill a YouTube title, description, and tags based on the
task's outline and full script. Returns None when ANTHROPIC_API_KEY is absent.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.task import Task
from sqlalchemy import select

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 1024


def _parse_metadata(raw: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    return {
        "title": str(data.get("title", "")),
        "description": str(data.get("description", "")),
        "tags": [str(t) for t in data.get("tags", [])],
    }


async def generate_youtube_metadata(task_id: str) -> dict[str, Any] | None:
    """
    Generate YouTube title, description, and tags for the task.

    Returns ``{"title": ..., "description": ..., "tags": [...]}`` or None.
    """
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — metadata generation skipped")
        return None

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            return None

        script = row.script or {}
        outline = script.get("outline", {})
        title = row.title or "Untitled"
        logline = outline.get("logline", "")
        genre = outline.get("genre", "")
        themes = outline.get("themes", [])
        synopsis = outline.get("synopsis", "")

    prompt = f"""You are a YouTube content strategist. Create SEO-optimised metadata for a video.

VIDEO DETAILS:
- Working Title: {title}
- Genre: {genre}
- Logline: {logline}
- Themes: {", ".join(themes) if isinstance(themes, list) else themes}
- Synopsis: {synopsis}

Return a JSON object with exactly these keys:
- "title": A compelling YouTube title (max 70 characters, no clickbait)
- "description": A 3–5 paragraph YouTube description with timestamps placeholder and call-to-action
- "tags": A list of 10–15 relevant tags (strings)

Return only the JSON object, no prose."""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        metadata = _parse_metadata(raw)
    except Exception as exc:
        logger.error("Metadata generation failed for task %s: %s", task_id, exc)
        return None

    # Persist into task.script
    async for db in get_db():
        db_row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if db_row:
            sc = dict(db_row.script or {})
            sc["youtube_metadata"] = metadata
            db_row.script = sc
            db.add(db_row)
            await db.commit()
        break

    logger.info("Metadata generated for task %s: '%s'", task_id, metadata.get("title"))
    return metadata
