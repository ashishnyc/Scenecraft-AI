"""Character consistency engine (Video Pipeline — SA-31).

Builds per-character reference prompts from the Character model, injects
them into video generation calls, and validates generated clips via
CLIP-score similarity against stored reference images.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_CLIP_SIMILARITY_THRESHOLD = 0.75


# ── Reference prompt builder ──────────────────────────────────────────────────

def build_character_reference_prompt(
    character_name: str,
    personality_prompt: str | None,
    visual_references: dict | None,
    appearance_override: dict | None,
) -> str:
    """
    Assemble a single reference prompt string for injection into video gen calls.

    Merges: base appearance description (visual_references) + LoRA trigger words
    + episode-specific appearance_override from the casting record.
    """
    parts: list[str] = [f"Character: {character_name}"]

    base = (visual_references or {}).get("base_description", "")
    if base:
        parts.append(f"Appearance: {base}")

    lora = (visual_references or {}).get("lora_trigger_words", "")
    if lora:
        parts.append(f"LoRA triggers: {lora}")

    override = appearance_override or {}
    if override:
        override_str = ", ".join(f"{k}: {v}" for k, v in override.items())
        parts.append(f"Episode override: {override_str}")

    return "; ".join(parts)


def build_cast_reference_prompts(
    cast: list[dict[str, Any]],
) -> dict[str, str]:
    """
    Build reference prompt map for all characters in *cast*.

    *cast* is a list of dicts with keys: name, personality_prompt,
    visual_references, appearance_override.

    Returns {character_name: reference_prompt_string}.
    """
    return {
        c["name"]: build_character_reference_prompt(
            c["name"],
            c.get("personality_prompt"),
            c.get("visual_references"),
            c.get("appearance_override"),
        )
        for c in cast
    }


def inject_character_references(
    shot_prompt: str,
    shot_characters: list[str],
    reference_prompts: dict[str, str],
) -> str:
    """Append character reference text to a video generation prompt."""
    refs = [reference_prompts[c] for c in shot_characters if c in reference_prompts]
    if not refs:
        return shot_prompt
    return shot_prompt + " | " + " | ".join(refs)


# ── CLIP similarity check ─────────────────────────────────────────────────────

def check_clip_similarity(
    frame_embedding: list[float],
    reference_embedding: list[float],
) -> float:
    """
    Compute cosine similarity between a frame embedding and a reference image embedding.
    Returns score in [0, 1].
    """
    import math
    dot = sum(a * b for a, b in zip(frame_embedding, reference_embedding))
    norm_a = math.sqrt(sum(a * a for a in frame_embedding))
    norm_b = math.sqrt(sum(b * b for b in reference_embedding))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def flag_low_similarity_shots(
    shot_similarities: dict[int, float],
    threshold: float = _CLIP_SIMILARITY_THRESHOLD,
) -> list[int]:
    """Return list of shot_indices where similarity is below *threshold*."""
    return [idx for idx, score in shot_similarities.items() if score < threshold]
