"""LLM-powered project name + video concept suggester."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a YouTube channel strategist. Given a free-text description of a channel concept,
suggest a project name and a set of base video ideas that every future episode will extend from.

Respond ONLY with a valid JSON object in this exact shape:
{
  "name": "Short compelling project name (3-6 words)",
  "series_concept": "One sentence describing the overarching series premise",
  "video_concepts": [
    {
      "title": "Video episode title",
      "concept": "2-3 sentence description of what this episode covers and how it fits the series"
    }
  ]
}

Rules:
- name: 3-6 words, title case, no punctuation
- series_concept: single sentence, max 25 words
- video_concepts: exactly 5 ideas
- Each concept must feel like a natural extension of the same series thread
- No markdown, no text outside the JSON
"""


def _parse_response(raw: str) -> dict:
    text = raw.strip()
    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    data = json.loads(text)

    if not data.get("name") or not data.get("video_concepts"):
        raise ValueError("Missing required fields in LLM response")
    if len(data["video_concepts"]) < 1:
        raise ValueError("No video concepts returned")

    return data


def suggest_project(brief: str) -> dict | None:
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
    )
    if raw is None:
        logger.warning("LLM unavailable — cannot generate project suggestions")
        return None

    try:
        return _parse_response(raw)
    except Exception as exc:
        logger.error("Failed to parse project suggestions: %s\nRaw: %s", exc, raw[:400])
        return None
