"""Editorial memory system (SA-56).

Learns creator preferences from review history (approve/reject/change-request
patterns) and surfaces them as personalised guidance for future generations.

What it learns:
  - Script style preferences (dialogue density, scene length, tone)
  - Audio preferences (which voice/character combos get approved vs changed)
  - Visual preferences (camera angles, environments flagged as "needs improvement")
  - Pacing preferences (shots flagged as too short/long)

Storage: preferences are stored in workspace.style_guide JSONB (extended) and
as vectors in Qdrant collection "editorial_memory" for semantic lookup.

The learning signal comes from:
  - Gate 1 review: audio approve vs request_changes + notes
  - Gate 2 review: video approve vs request_changes + flagged_shot_indices + notes
  - Status transitions logged in review_actions table
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.task import Task
from app.models.review_action import ReviewAction
from sqlalchemy import select

logger = logging.getLogger(__name__)

_COLLECTION = "editorial_memory"
_MODEL = "claude-haiku-4-5-20251001"


async def extract_preferences_from_review(task_id: str) -> dict[str, Any] | None:
    """
    Analyse a completed task's review history and extract preference signals.

    Returns a preference dict or None if insufficient data.
    """
    from app.services.llm_client import llm_chat

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            return None

        actions = (await db.execute(
            select(ReviewAction).where(ReviewAction.task_id == task_id)
            .order_by(ReviewAction.timestamp)
        )).scalars().all()

        script = row.script or {}
        audio_review = script.get("audio_review", {})
        video_review = script.get("video_review", {})
        break

    if not actions:
        return None

    # Build a review summary for the LLM
    review_notes = []
    for action in actions:
        if action.notes:
            review_notes.append(f"- [{action.action.value}] {action.notes}")

    audio_notes = audio_review.get("notes", "")
    video_notes = video_review.get("notes", "")
    flagged_shots = video_review.get("flagged_shot_indices", [])

    if not review_notes and not audio_notes and not video_notes:
        return None

    summary_text = "\n".join(review_notes)
    if audio_notes:
        summary_text += f"\nAudio review note: {audio_notes}"
    if video_notes:
        summary_text += f"\nVideo review note: {video_notes}"
    if flagged_shots:
        summary_text += f"\nFlagged shot indices: {flagged_shots}"

    prompt = f"""Analyse these creator review notes and extract editorial preferences as structured JSON.

REVIEW NOTES:
{summary_text}

Return a JSON object with these optional keys (only include keys where the notes reveal a clear preference):
- "tone_preference": string (e.g. "darker", "more comedic", "concise")
- "dialogue_style": string (e.g. "less dialogue", "more witty banter")
- "pacing": string (e.g. "faster cuts", "longer establishing shots")
- "audio_voice_notes": string (free text on voice/audio preferences)
- "visual_notes": string (free text on visual/camera preferences)
- "avoid": list of strings (things to avoid in future)
- "emphasise": list of strings (things to do more of)

Return only the JSON object."""

    try:
        raw = llm_chat(system="You are an editorial analyst. Return only JSON.", user=prompt, max_tokens=512)
        if raw is None:
            return None
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        import json
        preferences = json.loads(raw)
        logger.info("Extracted preferences from task %s: %s", task_id, list(preferences.keys()))
        return preferences
    except Exception as exc:
        logger.error("Preference extraction failed for task %s: %s", task_id, exc)
        return None


async def update_workspace_preferences(workspace_id: str, new_prefs: dict[str, Any]) -> None:
    """
    Merge newly extracted preferences into workspace.style_guide["editorial_memory"].
    """
    from app.models.workspace import Workspace

    async for db in get_db():
        ws = (await db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )).scalar_one_or_none()
        if not ws:
            return

        guide = dict(ws.style_guide or {})
        memory = guide.get("editorial_memory", {})

        # Merge: append to avoid/emphasise lists, overwrite scalar preferences
        for key, value in new_prefs.items():
            if key in ("avoid", "emphasise") and isinstance(value, list):
                existing = memory.get(key, [])
                merged = list(dict.fromkeys(existing + value))  # deduplicate preserving order
                memory[key] = merged[:50]  # cap at 50 items
            else:
                memory[key] = value  # latest preference wins

        guide["editorial_memory"] = memory
        ws.style_guide = guide
        db.add(ws)
        await db.commit()
        break

    logger.info("Updated editorial memory for workspace %s", workspace_id)


async def get_editorial_guidance(workspace_id: str) -> dict[str, Any]:
    """
    Return the current editorial memory for a workspace as LLM-injectable guidance.
    """
    from app.models.workspace import Workspace

    async for db in get_db():
        ws = (await db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )).scalar_one_or_none()
        if not ws:
            return {}
        guide = ws.style_guide or {}
        return guide.get("editorial_memory", {})

    return {}


def format_guidance_for_prompt(memory: dict[str, Any]) -> str:
    """Format editorial memory into a prompt injection block."""
    if not memory:
        return ""

    lines = ["CREATOR PREFERENCES (from past review history):"]
    for key, value in memory.items():
        if isinstance(value, list):
            lines.append(f"  {key}: {', '.join(str(v) for v in value[:10])}")
        else:
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)


async def run_post_publish_learning(task_id: str, workspace_id: str) -> None:
    """
    Extract preferences from a completed task and store them in workspace memory.
    Called after a task reaches 'published' status.
    """
    prefs = await extract_preferences_from_review(task_id)
    if prefs:
        await update_workspace_preferences(workspace_id, prefs)
        logger.info("Editorial memory updated for workspace %s from task %s", workspace_id, task_id)
