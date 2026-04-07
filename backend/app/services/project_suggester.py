"""LLM-powered project name + video concept suggester."""
from __future__ import annotations

import json
import logging
import re

from app.services.llm_client import AIConfig

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a YouTube channel strategist. Given a free-text description of a channel concept,
suggest a project name and a set of episode ideas that together form a coherent, binge-worthy series.

Respond ONLY with a valid JSON object in this exact shape:
{
  "name": "Short compelling project name (3-6 words)",
  "series_concept": "One sentence describing the overarching series premise",
  "video_concepts": [
    {
      "title": "Episode title (e.g. S01E01 – The Haunting of Harrow House)",
      "concept": "2-3 sentence description of what this episode covers, the hook, and how it advances the series arc"
    }
  ]
}

Rules:
- name: 3-6 words, title case, no punctuation
- series_concept: single sentence, max 25 words — describe the spine that connects ALL episodes
- video_concepts: exactly 5 episode ideas, numbered S01E01 through S01E05
- Each episode must feel like the next instalment of the same continuous series
- Build escalating tension or depth across the five episodes — they are not standalone
- No markdown, no text outside the JSON
"""


def _parse_response(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    data = json.loads(text)

    if not data.get("name") or not data.get("video_concepts"):
        raise ValueError("Missing required fields in LLM response")
    if len(data["video_concepts"]) < 1:
        raise ValueError("No video concepts returned")

    return data


GENERATE_SYSTEM_PROMPT = """\
You are a YouTube channel strategist. You are adding new episode ideas to an existing series.

You will be given:
- The series concept (overarching premise)
- Existing episode ideas already planned
- An optional additional brief or theme

Generate 5 NEW episode ideas that:
- Continue and deepen the same series arc
- Do not repeat or closely resemble the existing episodes
- Feel like the natural next instalments in the series
- Build on narrative threads from earlier episodes where appropriate

Respond ONLY with a valid JSON array of exactly 5 objects:
[
  {
    "title": "Episode title (e.g. S01E06 – Title Here)",
    "concept": "2-3 sentence description of what this episode covers and how it advances the series"
  }
]

No markdown, no text outside the JSON array.
"""


def suggest_project(brief: str, config: AIConfig | None = None) -> dict | None:
    """
    Call the LLM with a free-text brief and return suggested project metadata.
    Returns dict with keys: name, series_concept, video_concepts (list of {title, concept}).
    Returns None if LLM is unavailable or output is unparseable.
    """
    from app.services.llm_client import llm_chat

    if not brief or not brief.strip():
        return None

    raw = llm_chat(
        system=SYSTEM_PROMPT,
        user=f"Channel concept:\n{brief.strip()}",
        max_tokens=1024,
        temperature=0.8,
        config=config,
    )
    if raw is None:
        logger.warning("LLM unavailable — cannot generate project suggestions")
        return None

    try:
        return _parse_response(raw)
    except Exception as exc:
        logger.error("Failed to parse project suggestions: %s\nRaw: %s", exc, raw[:400])
        return None


def generate_concepts(
    brief: str,
    series_concept: str,
    existing_concepts: list[dict],
    config: AIConfig | None = None,
) -> list[dict] | None:
    """
    Generate additional episode concepts for an existing series.
    Returns list of {title, concept} dicts, or None on failure.
    """
    from app.services.llm_client import llm_chat

    existing_titles = "\n".join(
        f"- {c.get('title', '')}" for c in existing_concepts
    ) or "None yet"

    user_msg = (
        f"Series concept: {series_concept or brief}\n\n"
        f"Existing episodes:\n{existing_titles}\n\n"
        f"Additional context: {brief or 'Continue the series naturally'}"
    )

    raw = llm_chat(
        system=GENERATE_SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=1024,
        temperature=0.85,
        config=config,
    )
    if raw is None:
        logger.warning("LLM unavailable — cannot generate episode concepts")
        return None

    try:
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text.strip())
        data = json.loads(text)
        if not isinstance(data, list) or len(data) < 1:
            raise ValueError("Expected a JSON array")
        return data
    except Exception as exc:
        logger.error("Failed to parse generated concepts: %s\nRaw: %s", exc, raw[:400])
        return None
