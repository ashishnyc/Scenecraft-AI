"""Retry and partial failure recovery (SA-50).

Tracks which clips failed during generation and re-queues only those,
rather than re-running the entire video pipeline.

Storage: failed clip indices and their error messages are stored in
task.script["clip_failures"] as a list of {"shot_index": n, "error": "..."}.

The recovery flow:
  1. `record_clip_failure(task_id, shot_index, error)` — called from video_clip_generator on failure
  2. `get_failed_clips(task_id)` — returns list of shot indices to retry
  3. `retry_failed_clips(task_id)` — re-runs only the failed clips and merges results
  4. `clear_failures(task_id)` — called after successful recovery
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.task import Task
from sqlalchemy import select

logger = logging.getLogger(__name__)

_MAX_RETRIES_PER_CLIP = 3


async def record_clip_failure(task_id: str, shot_index: int, error: str) -> None:
    """Record a clip generation failure in task.script."""
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if row:
            sc = dict(row.script or {})
            failures: list[dict] = sc.get("clip_failures", [])

            # Update existing or append new
            existing = next((f for f in failures if f["shot_index"] == shot_index), None)
            if existing:
                existing["error"] = error
                existing["attempts"] = existing.get("attempts", 0) + 1
            else:
                failures.append({"shot_index": shot_index, "error": error, "attempts": 1})

            sc["clip_failures"] = failures
            row.script = sc
            db.add(row)
            await db.commit()
        break
    logger.warning("Recorded clip failure for task %s shot %d: %s", task_id, shot_index, error)


async def get_failed_clips(task_id: str) -> list[dict[str, Any]]:
    """Return list of failed clip records that haven't exceeded retry limit."""
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            return []
        failures = (row.script or {}).get("clip_failures", [])
        return [f for f in failures if f.get("attempts", 0) < _MAX_RETRIES_PER_CLIP]

    return []


async def retry_failed_clips(task_id: str) -> dict[str, Any]:
    """
    Re-queue failed clips (below retry limit) and merge with existing successes.

    Returns ``{"retried": n, "succeeded": n, "still_failed": n}``.
    """
    from app.services.video_clip_generator import generate_clips

    failed = await get_failed_clips(task_id)
    if not failed:
        logger.info("No retryable clip failures for task %s", task_id)
        return {"retried": 0, "succeeded": 0, "still_failed": 0}

    # Build a partial shot list for failed shots only
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            return {"retried": 0, "succeeded": 0, "still_failed": len(failed)}
        script = row.script or {}
        shot_list = script.get("shot_list", {})
        existing_clips = {int(k): v for k, v in script.get("clip_urls", {}).items()}
        break

    failed_indices = {f["shot_index"] for f in failed}
    retry_shot_list = {
        "shots": [s for s in shot_list.get("shots", []) if s["shot_index"] in failed_indices]
    }

    logger.info("Retrying %d failed clips for task %s", len(retry_shot_list["shots"]), task_id)
    new_clip_urls, cost = await generate_clips(task_id, retry_shot_list, None)

    succeeded = len(new_clip_urls)
    still_failed = len(failed_indices) - succeeded

    # Merge successful retries into clip_urls, clear recovered failures
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if row:
            sc = dict(row.script or {})
            merged = {**{str(k): v for k, v in existing_clips.items()},
                      **{str(k): v for k, v in new_clip_urls.items()}}
            sc["clip_urls"] = merged
            # Remove recovered failures
            sc["clip_failures"] = [
                f for f in sc.get("clip_failures", [])
                if f["shot_index"] not in new_clip_urls
            ]
            row.script = sc
            row.total_cost_usd = (row.total_cost_usd or Decimal("0")) + cost
            db.add(row)
            await db.commit()
        break

    logger.info("Retry complete for task %s: %d succeeded, %d still failed", task_id, succeeded, still_failed)
    return {"retried": len(failed), "succeeded": succeeded, "still_failed": still_failed}


async def clear_failures(task_id: str) -> None:
    """Clear all recorded clip failures (called after successful full pipeline run)."""
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if row:
            sc = dict(row.script or {})
            sc.pop("clip_failures", None)
            row.script = sc
            db.add(row)
            await db.commit()
        break


async def get_recovery_status(task_id: str) -> dict[str, Any]:
    """Return a summary of retry state for monitoring."""
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            return {"task_id": task_id, "failures": []}
        failures = (row.script or {}).get("clip_failures", [])
        retryable = [f for f in failures if f.get("attempts", 0) < _MAX_RETRIES_PER_CLIP]
        exhausted = [f for f in failures if f.get("attempts", 0) >= _MAX_RETRIES_PER_CLIP]
        return {
            "task_id": task_id,
            "total_failures": len(failures),
            "retryable": len(retryable),
            "exhausted": len(exhausted),
            "failures": failures,
        }

    return {"task_id": task_id, "failures": []}
