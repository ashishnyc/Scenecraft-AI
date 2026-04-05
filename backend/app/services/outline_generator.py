"""LLM-powered 3-act outline generator (Script Pipeline — Stage 1)."""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Output schema ─────────────────────────────────────────────────────────────

class Scene(BaseModel):
    scene_number: int
    location: str
    time_of_day: str
    summary: str
    characters_present: list[str] = Field(default_factory=list)


class Act(BaseModel):
    act_number: int
    title: str
    scenes: list[Scene]

    @model_validator(mode="after")
    def at_least_three_scenes(self) -> "Act":
        if len(self.scenes) < 3:
            raise ValueError(f"Act {self.act_number} must have at least 3 scenes, got {len(self.scenes)}")
        return self


class Outline(BaseModel):
    acts: list[Act]

    @model_validator(mode="after")
    def exactly_three_acts(self) -> "Outline":
        if len(self.acts) != 3:
            raise ValueError(f"Outline must have exactly 3 acts, got {len(self.acts)}")
        return self


# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a professional screenwriter and story structure expert.
Given a video concept brief, generate a structured 3-act outline for a YouTube video.

Respond ONLY with a valid JSON object matching this schema:
{
  "acts": [
    {
      "act_number": 1,
      "title": "string",
      "scenes": [
        {
          "scene_number": 1,
          "location": "string",
          "time_of_day": "string (e.g. Day, Night, Dawn)",
          "summary": "string (2-4 sentences)",
          "characters_present": ["character name", ...]
        }
      ]
    }
  ]
}

Rules:
- Exactly 3 acts
- At least 3 scenes per act
- scene_number is globally sequential (1, 2, 3, ... across all acts)
- Characters must only come from the provided cast list (or be empty if no cast)
- No markdown, no explanation outside the JSON
"""


def _build_prompt(
    concept_brief: str,
    creator_notes: str | None,
    style_guide: dict,
    cast_names: list[str],
    story_bible: dict | None = None,
) -> str:
    cast_text = ", ".join(cast_names) if cast_names else "No cast defined — leave characters_present empty"
    notes_text = creator_notes or "None"
    style_text = json.dumps(style_guide, indent=2) if style_guide else "Not specified"

    bible_section = ""
    if story_bible:
        char_states = story_bible.get("character_states", {})
        open_threads = [t for t in story_bible.get("plot_threads", []) if t.get("status") == "open"]
        world_building = story_bible.get("world_building", [])
        prev_eps = story_bible.get("previous_episodes", [])
        bible_section = f"""
Series continuity (story bible):
  Character states: {json.dumps(char_states) if char_states else "None yet"}
  Open plot threads: {json.dumps(open_threads) if open_threads else "None"}
  World-building rules: {"; ".join(world_building) if world_building else "None"}
  Previous episodes: {len(prev_eps)} episode(s) — last: {prev_eps[-1].get("summary", "") if prev_eps else "N/A"}
"""

    return f"""\
Concept brief:
{concept_brief}

Creator notes:
{notes_text}

Style guide:
{style_text}

Available cast: {cast_text}
{bible_section}
Generate the 3-act outline now.
"""


def _parse_outline(raw: str, cast_names: list[str] | None = None) -> Outline:
    """Parse and validate LLM JSON output into an Outline.

    If *cast_names* is provided, raises ValueError when the outline contains
    a character name that is not in the cast.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    data = json.loads(text)
    outline = Outline(**data)

    if cast_names:
        allowed = {n.lower() for n in cast_names}
        for act in outline.acts:
            for scene in act.scenes:
                for char in scene.characters_present:
                    if char.lower() not in allowed:
                        raise ValueError(
                            f"Character '{char}' in scene {scene.scene_number} is not in the project cast"
                        )

    return outline


# ── Main entry point ──────────────────────────────────────────────────────────

async def generate_outline(
    task_id: str,
    concept_brief: str,
    creator_notes: str | None,
    style_guide: dict,
    cast_names: list[str],
    story_bible: dict | None = None,
) -> dict[str, Any] | None:
    """
    Call Claude to produce a 3-act outline for the given task.
    For serialised projects, pass *story_bible* to inject series continuity.
    Returns the validated outline dict, or None on failure.
    """
    settings = get_settings()

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping outline generation for task %s", task_id)
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    user_prompt = _build_prompt(concept_brief, creator_notes, style_guide, cast_names, story_bible)

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = message.content[0].text
    except Exception as exc:
        logger.error("LLM call failed for outline (task %s): %s", task_id, exc)
        return None

    try:
        outline = _parse_outline(raw, cast_names=cast_names)
        logger.info("Outline generated for task %s (%d acts)", task_id, len(outline.acts))
        return outline.model_dump()
    except (json.JSONDecodeError, Exception) as exc:
        logger.error("Failed to parse outline for task %s: %s\nRaw: %s", task_id, exc, raw[:500])
        return None
