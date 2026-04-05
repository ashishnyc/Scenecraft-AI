"""Scene-level re-edit pipeline (SA-41).

When a creator flags specific shots during video review (Gate 2), this service
re-generates only those clips rather than re-running the entire video pipeline.

Flow:
  1. Read flagged_shot_indices from task.script["video_review"]
  2. Re-generate clips for those shots via video_clip_generator
  3. Re-assemble the final video with the new clips replacing the old ones
  4. Run QC and update task.script accordingly
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.task import Task
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def re_edit_flagged_scenes(task_id: str) -> dict[str, Any] | None:
    """
    Re-generate clips for flagged shots and re-assemble the video.

    Returns the new quality report dict, or None on failure.
    """
    from app.services.video_clip_generator import generate_clips
    from app.services.video_assembler import assemble_video
    from app.services.video_quality_checker import check_quality

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            logger.error("Task %s not found for re-edit", task_id)
            return None

        script = dict(row.script or {})
        shot_list = script.get("shot_list", {})
        clip_urls: dict[int, str] = script.get("clip_urls", {})
        audio_stems = script.get("audio_stems")
        music_urls: dict[int, str] = script.get("music_urls", {})
        video_review = script.get("video_review", {})
        flagged_indices: list[int] = video_review.get("flagged_shot_indices", [])

        if not flagged_indices:
            logger.info("No flagged shots for task %s — nothing to re-edit", task_id)
            return script.get("quality_report")

        title = row.title or "Untitled"
        break

    if not shot_list.get("shots"):
        logger.error("No shot list found for task %s", task_id)
        return None

    # Build a partial shot list for only flagged shots
    flagged_set = set(flagged_indices)
    flagged_shots = {
        "shots": [s for s in shot_list["shots"] if s["shot_index"] in flagged_set]
    }

    logger.info("Re-generating %d flagged clips for task %s", len(flagged_shots["shots"]), task_id)

    # Re-generate only flagged clips
    new_clip_urls, clip_cost = await generate_clips(task_id, flagged_shots, None)
    if not new_clip_urls:
        logger.error("Clip re-generation failed for task %s", task_id)
        return None

    # Merge new clips with existing ones (replacing flagged indices)
    merged_clip_urls = {**{int(k): v for k, v in clip_urls.items()}, **new_clip_urls}

    # Re-assemble full video with updated clips
    final_url = await assemble_video(
        task_id=task_id,
        shot_list=shot_list,
        clip_s3_urls=merged_clip_urls,
        audio_stems=audio_stems,
        music_s3_urls={int(k): v for k, v in music_urls.items()},
        title=title,
    )
    if not final_url:
        logger.error("Video re-assembly failed for task %s", task_id)
        return None

    # QC check
    quality_report = await check_quality(task_id, final_url, shot_list, audio_stems)

    # Persist updated state
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if row:
            sc = dict(row.script or {})
            sc["clip_urls"] = {str(k): v for k, v in merged_clip_urls.items()}
            sc["final_video_url"] = final_url
            sc["quality_report"] = quality_report
            # Clear the flagged list now that re-edit is done
            sc.setdefault("video_review", {})["flagged_shot_indices"] = []
            row.script = sc
            row.final_video_url = final_url
            # Accumulate cost
            from decimal import Decimal
            row.total_cost_usd = (row.total_cost_usd or Decimal("0")) + clip_cost
            db.add(row)
            await db.commit()
        break

    logger.info("Re-edit complete for task %s, QC passed=%s", task_id, quality_report and quality_report.get("passed"))
    return quality_report
