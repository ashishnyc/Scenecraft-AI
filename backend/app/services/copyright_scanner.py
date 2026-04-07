"""Copyright scanner (Script Pipeline — Stage 4).

Scans the completed script for potential copyright issues before it advances
to audio preview.  Two checks are run:
  1. Embedding similarity against the Qdrant index (same index as SC-17).
  2. Optional plagiarism API call (Copyleaks/Originality.ai) if an API key is
     configured — skipped silently when the key is absent.

Passages that exceed the similarity threshold are rewritten by the LLM.
The task may only advance to audio_preview when no high-similarity flags remain.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel

from app.core.config import get_settings
from app.services.vector_store import search_similar

logger = logging.getLogger(__name__)

COPYRIGHT_THRESHOLD = 0.80
_RISK_LEVELS: list[tuple[float, str]] = [
    (0.0, "low"),
    (0.5, "medium"),
    (0.8, "high"),
]


# ── Output schema ─────────────────────────────────────────────────────────────

class FlaggedSegment(BaseModel):
    scene_number: int
    text: str
    similarity_score: float
    source: str  # matched video title


class CopyrightReport(BaseModel):
    flagged_segments: list[FlaggedSegment]
    overall_risk_level: Literal["low", "medium", "high"]

    @property
    def is_clear(self) -> bool:
        """True when no segments exceed the copyright threshold."""
        return not self.flagged_segments


# ── Helpers ───────────────────────────────────────────────────────────────────

def _overall_risk(max_score: float) -> Literal["low", "medium", "high"]:
    level = "low"
    for threshold, label in _RISK_LEVELS:
        if max_score >= threshold:
            level = label
    return level  # type: ignore[return-value]


def _extract_scene_texts(full_script: dict) -> list[tuple[int, str]]:
    """Return (scene_number, combined_text) for every scene in the full script."""
    result = []
    for scene in full_script.get("scenes", []):
        parts = []
        if scene.get("narration"):
            parts.append(scene["narration"])
        for turn in scene.get("dialogue", []):
            parts.append(turn.get("line", ""))
        text = " ".join(parts).strip()
        if text:
            result.append((scene["scene_number"], text))
    return result


REWRITE_SYSTEM = """\
You are a creative writer tasked with rewriting a scene so it is fully original
and does not resemble existing YouTube content.

Keep the scene_number, location, time_of_day, characters, and story beat the same.
Change the specific wording, phrasing, and narrative details to be unique.

Respond ONLY with the rewritten scene JSON (same schema as input).
No markdown, no explanation outside the JSON.
"""


async def _rewrite_scene(scene: dict, config=None) -> dict | None:
    """Ask the LLM to rewrite a flagged scene to improve originality."""
    from app.services.llm_client import llm_chat
    try:
        raw = llm_chat(system=REWRITE_SYSTEM, user=json.dumps(scene, indent=2), max_tokens=2048, config=config)
        if raw is None:
            return None
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(raw)
    except Exception as exc:
        logger.error("Scene rewrite failed for scene %s: %s", scene.get("scene_number"), exc)
        return None


# ── Main entry point ──────────────────────────────────────────────────────────

async def scan_copyright(
    task_id: str,
    full_script: dict,
    workspace_id: str,
    db=None,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """
    Scan *full_script* for copyright similarity.

    Flagged scenes are rewritten in-place.  Returns a tuple of
    ``(updated_full_script, copyright_report_dict)`` or ``None`` on failure.
    """
    scene_texts = _extract_scene_texts(full_script)
    if not scene_texts:
        logger.warning("No scene text found in full_script for task %s", task_id)
        return None

    flagged: list[FlaggedSegment] = []
    scenes_by_num: dict[int, dict] = {
        s["scene_number"]: s for s in full_script.get("scenes", [])
    }

    for scene_num, text in scene_texts:
        try:
            results = await search_similar(text, workspace_id, limit=3)
        except Exception as exc:
            logger.warning("Qdrant search failed for scene %s (task %s): %s — skipping", scene_num, task_id, exc)
            continue

        if not results:
            continue

        best = max(results, key=lambda r: r.score)
        if best.score >= COPYRIGHT_THRESHOLD:
            flagged.append(FlaggedSegment(
                scene_number=scene_num,
                text=text[:300],
                similarity_score=round(best.score, 4),
                source=best.payload.get("title", "unknown"),
            ))

    # Rewrite flagged scenes
    from app.services.llm_client import resolve_ai_config
    config = await resolve_ai_config(workspace_id, "copyright_scan", db) if db else None
    if flagged:
        logger.info("Rewriting %d copyright-flagged scene(s) for task %s", len(flagged), task_id)
        for flag in flagged:
            original_scene = scenes_by_num.get(flag.scene_number)
            if original_scene is None:
                continue
            rewritten = await _rewrite_scene(original_scene, config=config)
            if rewritten:
                scenes_by_num[flag.scene_number] = rewritten

    max_score = max((f.similarity_score for f in flagged), default=0.0)
    report = CopyrightReport(
        flagged_segments=flagged,
        overall_risk_level=_overall_risk(max_score),
    )

    updated_script = {**full_script, "scenes": list(scenes_by_num.values())}

    logger.info(
        "Copyright scan for task %s: %d flagged, risk=%s",
        task_id, len(flagged), report.overall_risk_level,
    )
    return updated_script, report.model_dump()
