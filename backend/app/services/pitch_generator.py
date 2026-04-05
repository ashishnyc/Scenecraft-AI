"""LLM-powered pitch generator using Claude API."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pitch import Pitch
from app.schemas.pitch import PitchData

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a creative YouTube content strategist. Given workspace context and trending signals,
generate compelling video pitch ideas.

Always respond with a JSON array of pitch objects. Each object must have:
- "title": string (catchy video title, 5-80 chars)
- "concept_summary": string (what the video is about, 50-300 words)
- "target_audience_hook": string (one sentence explaining why viewers will click, max 100 words)
- "appeal_score": number (0-10 estimated audience appeal based on trend strength)

Respond ONLY with valid JSON — no markdown, no explanation outside the JSON.
"""


def _build_user_prompt(
    workspace_name: str,
    style_guide: dict,
    trending_topics: list[dict],
    competitor_top_videos: list[dict],
    count: int,
) -> str:
    topics_text = "\n".join(
        f"- {t['topic']} (score={t['score']:.2f}, source={t['source']})"
        for t in trending_topics[:10]
    ) or "No trending topics available."

    competitor_text = "\n".join(
        f"- \"{v['title']}\" — {v['view_count']:,} views"
        for v in competitor_top_videos[:5]
        if v.get("title")
    ) or "No competitor data available."

    return f"""\
Workspace: {workspace_name}
Style guide: {json.dumps(style_guide, indent=2) if style_guide else "Not specified"}

Trending topics right now:
{topics_text}

Top competitor videos:
{competitor_text}

Generate exactly {count} video pitch idea(s) inspired by these signals.
Return a JSON array with {count} pitch object(s).
"""


def _parse_llm_response(raw: str) -> list[PitchData]:
    """Parse and validate LLM JSON output. Returns validated PitchData objects."""
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    data = json.loads(text)
    if not isinstance(data, list):
        data = [data]

    validated: list[PitchData] = []
    for item in data:
        try:
            validated.append(PitchData(**item))
        except (ValidationError, TypeError) as exc:
            logger.warning("Skipping invalid pitch: %s — %s", item.get("title"), exc)

    return validated


async def generate_pitches(
    workspace_id: str,
    workspace_name: str,
    style_guide: dict,
    trending_topics: list[dict],
    competitor_top_videos: list[dict],
    db: AsyncSession,
    count: int = 3,
) -> list[Pitch]:
    """
    Call Claude to generate `count` pitches and persist them.
    Falls back gracefully if ANTHROPIC_API_KEY is not set.
    """
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping pitch generation")
        return []

    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    user_prompt = _build_user_prompt(
        workspace_name, style_guide, trending_topics, competitor_top_videos, count
    )

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_output = message.content[0].text
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return []

    try:
        pitch_data_list = _parse_llm_response(raw_output)
    except (json.JSONDecodeError, Exception) as exc:
        logger.error("Failed to parse LLM output: %s\nRaw: %s", exc, raw_output[:500])
        return []

    from app.services.originality_checker import check_pitch_originality

    saved: list[Pitch] = []
    for pd in pitch_data_list:
        # Run originality check before saving
        pitch_text = f"{pd.title} {pd.concept_summary}"
        originality = await check_pitch_originality(pitch_text, workspace_id)

        status = "low_originality" if originality["low_originality"] else "pending"

        pitch = Pitch(
            id=uuid.uuid4(),
            workspace_id=uuid.UUID(workspace_id),
            title=pd.title,
            concept_summary=pd.concept_summary,
            target_audience_hook=pd.target_audience_hook,
            appeal_score=pd.appeal_score,
            source_topics=[t["topic"] for t in trending_topics[:5]],
            raw_llm_output=raw_output,
            originality_score=originality["originality_score"],
            similar_videos=originality["similar_videos"],
            status=status,
            created_at=datetime.now(tz=timezone.utc),
        )
        db.add(pitch)
        saved.append(pitch)

    await db.commit()
    for p in saved:
        await db.refresh(p)

    logger.info("Generated %d pitches for workspace %s", len(saved), workspace_id)
    return saved
