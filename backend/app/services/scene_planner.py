"""Scene planner (Video Pipeline — SA-30).

Takes the approved script and audio stem timing data, then uses an LLM to
break each scene into individual shots (4–10 s each) with camera, character,
environment, and mood metadata.

Shot list stored in task.script["shot_list"].
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_MIN_SHOT_DURATION = 4
_MAX_SHOT_DURATION = 10


# ── Schema ────────────────────────────────────────────────────────────────────

class Shot(BaseModel):
    shot_index: int
    scene_number: int
    duration_seconds: float = Field(ge=_MIN_SHOT_DURATION, le=_MAX_SHOT_DURATION)
    characters: list[str] = Field(default_factory=list)
    environment: str
    camera_angle: str
    action_description: str
    mood: str

    @model_validator(mode="after")
    def duration_in_range(self) -> "Shot":
        if not (_MIN_SHOT_DURATION <= self.duration_seconds <= _MAX_SHOT_DURATION):
            raise ValueError(
                f"Shot duration {self.duration_seconds}s outside [{_MIN_SHOT_DURATION}, {_MAX_SHOT_DURATION}]"
            )
        return self


class ShotList(BaseModel):
    shots: list[Shot]

    @model_validator(mode="after")
    def not_empty(self) -> "ShotList":
        if not self.shots:
            raise ValueError("Shot list must contain at least one shot")
        return self


# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a professional video director breaking a YouTube script into a shot list.
Each scene must be split into 2–8 individual shots of 4–10 seconds each.

Respond ONLY with a valid JSON object:
{
  "shots": [
    {
      "shot_index": <global int, starts at 0>,
      "scene_number": <int>,
      "duration_seconds": <float 4.0–10.0>,
      "characters": ["name", ...],
      "environment": "<brief env name, e.g. Victorian manor hallway>",
      "camera_angle": "<e.g. wide, medium, close-up, over-shoulder>",
      "action_description": "<what happens in this shot>",
      "mood": "<e.g. tense, hopeful, mysterious>"
    }
  ]
}

Rules:
- shot_index is globally sequential across all scenes (0, 1, 2, …)
- Total shots should be proportional to scene count (aim for 3–5 shots per scene)
- No markdown, no explanation outside the JSON
"""


def _build_prompt(full_script: dict, audio_stems: dict | None) -> str:
    scene_durations: dict[int, float] = {}
    if audio_stems:
        chapter_ts = audio_stems.get("chapter_timestamps", {})
        stems = audio_stems.get("stems", [])
        for scene_num, start_ms in chapter_ts.items():
            scene_stems = [s for s in stems if s["scene_number"] == int(scene_num)]
            total_ms = sum(s.get("duration_ms", 0) for s in scene_stems)
            scene_durations[int(scene_num)] = round(total_ms / 1000, 1)

    scenes_summary = []
    for scene in full_script.get("scenes", []):
        sn = scene.get("scene_number", 0)
        duration_hint = scene_durations.get(sn)
        hint_str = f" (~{duration_hint}s audio)" if duration_hint else ""
        scenes_summary.append(
            f"Scene {sn}{hint_str}: {scene.get('narration', '')[:150]}"
        )

    return f"""Script scenes:\n""" + "\n".join(scenes_summary) + "\n\nGenerate the shot list now."


def _parse_shot_list(raw: str) -> ShotList:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return ShotList(**json.loads(text))


# ── Entry point ───────────────────────────────────────────────────────────────

async def plan_shots(
    task_id: str,
    full_script: dict,
    audio_stems: dict | None,
) -> dict[str, Any] | None:
    """Generate a shot list for *full_script*. Returns ShotList dict or None."""
    from app.services.llm_client import llm_chat

    prompt = _build_prompt(full_script, audio_stems)
    raw = llm_chat(system=SYSTEM_PROMPT, user=prompt, max_tokens=8192)
    if raw is None:
        logger.warning("LLM unavailable — skipping scene planner for task %s", task_id)
        return None

    try:
        shot_list = _parse_shot_list(raw)
        logger.info("Shot list generated: %d shots for task %s", len(shot_list.shots), task_id)
        return shot_list.model_dump()
    except Exception as exc:
        logger.error("Failed to parse shot list (task %s): %s\nRaw: %s", task_id, exc, raw[:500])
        return None
