"""LLM-powered scene expander (Script Pipeline — Stage 2).

Takes the 3-act outline produced by stage 1 and expands every scene into
full screenplay format: narration, dialogue, visual direction, and an
estimated duration.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ── Output schema ─────────────────────────────────────────────────────────────

class DialogueLine(BaseModel):
    character: str
    line: str


class ExpandedScene(BaseModel):
    scene_number: int
    narration: str
    dialogue: list[DialogueLine] = Field(default_factory=list)
    visual_direction: str
    estimated_duration_seconds: int


class FullScript(BaseModel):
    scenes: list[ExpandedScene]

    @model_validator(mode="after")
    def at_least_one_scene(self) -> "FullScript":
        if not self.scenes:
            raise ValueError("full_script must contain at least one scene")
        return self


# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a professional screenwriter specialising in YouTube video scripts.
Given a scene summary and context, expand it into full screenplay format.

Respond ONLY with a valid JSON object matching this schema:
{
  "scene_number": <int>,
  "narration": "<opening or bridging narration text>",
  "dialogue": [
    {"character": "<name from cast>", "line": "<spoken line>"}
  ],
  "visual_direction": "<camera angles, props, action notes>",
  "estimated_duration_seconds": <int>
}

Rules:
- narration and visual_direction must be non-empty strings
- dialogue may be an empty list if the scene has no spoken lines
- Only characters listed in the provided cast may appear in dialogue
- estimated_duration_seconds should reflect the expected on-screen time (30–300)
- No markdown, no explanation outside the JSON
"""


def _build_scene_prompt(
    scene: dict,
    cast_profiles: dict[str, str | None],
    previous_scenes: list[dict],
) -> str:
    cast_text = "\n".join(
        f"  - {name}: {bio or 'No personality notes'}"
        for name, bio in cast_profiles.items()
    ) or "  No cast defined — dialogue list must be empty"

    context_text = "None (this is the first scene)" if not previous_scenes else (
        "\n".join(
            f"  Scene {s['scene_number']}: {s.get('narration', '')[:120]}..."
            for s in previous_scenes[-3:]  # last 3 scenes for context window efficiency
        )
    )

    characters_in_scene = ", ".join(scene.get("characters_present", [])) or "None"

    return f"""\
Scene to expand:
  scene_number: {scene['scene_number']}
  location: {scene.get('location', 'Unknown')}
  time_of_day: {scene.get('time_of_day', 'Unknown')}
  summary: {scene['summary']}
  characters_present: {characters_in_scene}

Cast profiles:
{cast_text}

Previous scenes context (for continuity):
{context_text}

Expand this scene now.
"""


def _parse_expanded_scene(
    raw: str,
    cast_names: list[str],
) -> ExpandedScene:
    """Parse LLM output and validate character names in dialogue."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    data = json.loads(text)
    scene = ExpandedScene(**data)

    if cast_names:
        allowed = {n.lower() for n in cast_names}
        for turn in scene.dialogue:
            if turn.character.lower() not in allowed:
                raise ValueError(
                    f"Character '{turn.character}' in scene {scene.scene_number} "
                    "dialogue is not in the project cast"
                )

    return scene


# ── Main entry point ──────────────────────────────────────────────────────────

async def expand_scenes(
    task_id: str,
    outline: dict,
    cast_profiles: dict[str, str | None],
) -> dict[str, Any] | None:
    """
    Expand every scene in *outline* into full screenplay format.

    *cast_profiles* maps character name → personality_prompt (may be None).

    Returns ``{"scenes": [...]}`` on success, or ``None`` on any failure.
    """
    settings = get_settings()

    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping scene expansion for task %s", task_id)
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    cast_names = list(cast_profiles.keys())
    scenes_flat: list[dict] = [
        scene
        for act in outline.get("acts", [])
        for scene in act.get("scenes", [])
    ]

    if not scenes_flat:
        logger.warning("No scenes found in outline for task %s", task_id)
        return None

    expanded: list[dict] = []

    for scene in scenes_flat:
        prompt = _build_scene_prompt(scene, cast_profiles, expanded)

        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text
        except Exception as exc:
            logger.error(
                "LLM call failed for scene %s (task %s): %s",
                scene.get("scene_number"), task_id, exc,
            )
            return None

        try:
            expanded_scene = _parse_expanded_scene(raw, cast_names)
            expanded.append(expanded_scene.model_dump())
        except (json.JSONDecodeError, Exception) as exc:
            logger.error(
                "Failed to parse scene %s (task %s): %s\nRaw: %s",
                scene.get("scene_number"), task_id, exc, raw[:500],
            )
            return None

    try:
        full_script = FullScript(scenes=expanded)
        logger.info("Scene expansion complete for task %s (%d scenes)", task_id, len(expanded))
        return full_script.model_dump()
    except Exception as exc:
        logger.error("FullScript assembly failed for task %s: %s", task_id, exc)
        return None
