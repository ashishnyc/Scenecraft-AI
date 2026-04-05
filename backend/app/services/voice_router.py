"""Script-to-audio voice router (Audio Pipeline — SA-24).

Parses the full_script and builds a flat routing manifest that maps every
line of text to the correct voice_profile_id.  Narration lines use the
workspace narrator voice; dialogue lines use the character's voice profile,
falling back to the narrator if none is configured.
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

NARRATOR_CHARACTER = "narrator"


class RoutingEntry(BaseModel):
    line_index: int
    scene_number: int
    text: str
    voice_profile_id: str
    character_name: str
    line_type: Literal["narration", "dialogue"]


def build_routing_manifest(
    full_script: dict,
    cast_voice_profiles: dict[str, str | None],
    narrator_voice_id: str,
) -> list[dict]:
    """
    Build a flat routing manifest from *full_script*.

    *cast_voice_profiles* maps character name (case-insensitive key) to their
    voice_profile_id (may be None if not yet assigned).

    *narrator_voice_id* is the workspace-level narrator voice used for all
    narration lines and as fallback for characters without a voice profile.

    Returns a list of ``RoutingEntry`` dicts ordered by line_index.
    """
    # Normalise cast lookup to lowercase keys
    cast_lower: dict[str, str | None] = {k.lower(): v for k, v in cast_voice_profiles.items()}

    entries: list[dict] = []
    line_index = 0

    for scene in full_script.get("scenes", []):
        scene_number = scene.get("scene_number", 0)

        # Narration line
        narration = (scene.get("narration") or "").strip()
        if narration:
            entries.append(RoutingEntry(
                line_index=line_index,
                scene_number=scene_number,
                text=narration,
                voice_profile_id=narrator_voice_id,
                character_name=NARRATOR_CHARACTER,
                line_type="narration",
            ).model_dump())
            line_index += 1

        # Dialogue lines
        for turn in scene.get("dialogue", []):
            text = (turn.get("line") or "").strip()
            character = (turn.get("character") or "").strip()
            if not text:
                continue

            voice_id = cast_lower.get(character.lower())
            if not voice_id:
                logger.warning(
                    "Character '%s' has no voice profile — falling back to narrator voice", character
                )
                voice_id = narrator_voice_id

            entries.append(RoutingEntry(
                line_index=line_index,
                scene_number=scene_number,
                text=text,
                voice_profile_id=voice_id,
                character_name=character,
                line_type="dialogue",
            ).model_dump())
            line_index += 1

    return entries
