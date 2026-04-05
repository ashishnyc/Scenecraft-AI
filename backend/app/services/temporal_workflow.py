"""Temporal workflow definition (SA-48).

Defines the video production pipeline as a Temporal workflow DAG so that:
  - Each stage runs as a separate Activity with timeouts and retries
  - Failures in one stage don't lose prior completed work
  - The workflow can be paused at Gate 1 (audio review) and Gate 2 (video review)
  - Partial restarts only re-run failed activities

Requires the Temporal server to be running (via docker-compose or cloud).
Worker entry point: ``python -m app.services.temporal_worker``

Workflow stages (mirrors the task status machine):
  1. outline          → SA-19/20/21/22/23
  2. audio_pipeline   → SA-24/25/26
  3. [GATE 1 — human audio review]
  4. video_pipeline   → SA-30/31/32/33/34/35/36
  5. [GATE 2 — human video review]
  6. publish          → SA-43/44
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ── Activity definitions ──────────────────────────────────────────────────────
# Activities are thin wrappers around existing services.
# They are registered with the Temporal worker in temporal_worker.py.

try:
    from temporalio import activity, workflow
    from temporalio.common import RetryPolicy
    _TEMPORAL_AVAILABLE = True
except ImportError:
    _TEMPORAL_AVAILABLE = False
    # Provide no-op stubs so the module can be imported without temporalio installed
    class _Stub:
        @staticmethod
        def defn(cls=None, **kwargs):
            return cls if cls else lambda c: c
        @staticmethod
        def run(fn): return fn
        @staticmethod
        def activity(fn=None, **kwargs):
            return fn if fn else lambda f: f

    class workflow:  # type: ignore
        defn = staticmethod(lambda **kw: lambda cls: cls)
        run = staticmethod(lambda fn: fn)
        sleep = None

    class activity:  # type: ignore
        defn = staticmethod(lambda fn=None, **kw: fn if fn else lambda f: f)
        execute_activity = None

    class RetryPolicy:  # type: ignore
        def __init__(self, **kwargs): pass


_DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_attempts=3,
    maximum_interval=timedelta(minutes=5),
)

_SCHEDULE_TO_CLOSE = timedelta(hours=2)


# ── Activity implementations ──────────────────────────────────────────────────

async def activity_run_outline(task_id: str) -> dict[str, Any]:
    """SA-19–23: Outline → scene expand → consistency → copyright → story bible."""
    from app.services.outline_generator import generate_outline
    from app.services.scene_expander import expand_scenes
    from app.services.consistency_checker import check_consistency
    from app.services.copyright_scanner import scan_copyright
    from app.db.postgres import AsyncSessionLocal
    from app.models.task import Task
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()
        cast = task.script.get("cast_profiles", []) if task.script else []
        outline = await generate_outline(task_id, task.concept_brief or "", cast_profiles=cast)
        if not outline:
            raise RuntimeError(f"Outline generation failed for task {task_id}")

        full_script = await expand_scenes(task_id, outline, cast)
        if not full_script:
            raise RuntimeError(f"Scene expansion failed for task {task_id}")

        full_script, consistency_report = await check_consistency(task_id, full_script, cast)
        updated_script, copyright_report = await scan_copyright(task_id, full_script) or (full_script, {})

        task.script = {**(task.script or {}), "outline": outline, "full_script": updated_script,
                       "consistency_report": consistency_report, "copyright_report": copyright_report}
        task.status = "audio_preview"
        db.add(task)
        await db.commit()

    return {"status": "outline_complete", "task_id": task_id}


async def activity_run_audio(task_id: str) -> dict[str, Any]:
    """SA-24–26: Voice routing → synthesis → assembly."""
    from app.api.tasks import _run_audio_pipeline
    await _run_audio_pipeline(task_id, None)
    return {"status": "audio_complete", "task_id": task_id}


async def activity_run_video(task_id: str) -> dict[str, Any]:
    """SA-30–36: Shot planning → clips → music → assembly → QC."""
    from app.api.tasks import _run_video_pipeline
    await _run_video_pipeline(task_id)
    return {"status": "video_complete", "task_id": task_id}


async def activity_run_publish(task_id: str) -> dict[str, Any]:
    """SA-43–44: Schedule and upload to YouTube."""
    from app.services.upload_scheduler import schedule_upload
    from app.services.youtube_uploader import upload_to_youtube

    schedule_info = await schedule_upload(task_id)
    video_id = await upload_to_youtube(task_id)
    return {"status": "published", "task_id": task_id, "youtube_video_id": video_id,
            "schedule": schedule_info}


async def activity_wait_for_gate(task_id: str, gate: str) -> dict[str, Any]:
    """Poll task status until a human approves the gate (status advances past it)."""
    from app.db.postgres import AsyncSessionLocal
    from app.models.task import Task
    from sqlalchemy import select
    import asyncio

    gate_passed_statuses = {
        "gate1": {"script_review", "producing", "final_review", "scheduled", "published"},
        "gate2": {"scheduled", "published"},
    }
    passed = gate_passed_statuses.get(gate, set())
    poll_interval = 30  # seconds
    max_wait = 7 * 24 * 3600  # 1 week

    elapsed = 0
    while elapsed < max_wait:
        async with AsyncSessionLocal() as db:
            task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
            if task and task.status.value in passed:
                return {"gate": gate, "passed": True, "status": task.status.value}
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError(f"Gate {gate} not cleared within 1 week for task {task_id}")


# ── Workflow definition ───────────────────────────────────────────────────────

if _TEMPORAL_AVAILABLE:
    @workflow.defn(name="VideoProductionWorkflow")
    class VideoProductionWorkflow:
        """Full video production DAG from concept to published YouTube video."""

        @workflow.run
        async def run(self, task_id: str) -> dict[str, Any]:
            from temporalio import workflow as wf

            execute = wf.execute_activity

            # Stage 1: Script pipeline
            await execute(
                activity_run_outline,
                task_id,
                schedule_to_close_timeout=_SCHEDULE_TO_CLOSE,
                retry_policy=_DEFAULT_RETRY,
            )

            # Stage 2: Audio pipeline
            await execute(
                activity_run_audio,
                task_id,
                schedule_to_close_timeout=_SCHEDULE_TO_CLOSE,
                retry_policy=_DEFAULT_RETRY,
            )

            # Gate 1: Wait for human audio approval
            await execute(
                activity_wait_for_gate,
                args=[task_id, "gate1"],
                schedule_to_close_timeout=timedelta(days=7),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )

            # Stage 3: Video pipeline
            await execute(
                activity_run_video,
                task_id,
                schedule_to_close_timeout=timedelta(hours=4),
                retry_policy=_DEFAULT_RETRY,
            )

            # Gate 2: Wait for human video approval
            await execute(
                activity_wait_for_gate,
                args=[task_id, "gate2"],
                schedule_to_close_timeout=timedelta(days=7),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )

            # Stage 4: Publish
            result = await execute(
                activity_run_publish,
                task_id,
                schedule_to_close_timeout=_SCHEDULE_TO_CLOSE,
                retry_policy=_DEFAULT_RETRY,
            )

            return result


async def start_workflow(task_id: str) -> str | None:
    """Start a VideoProductionWorkflow for the given task. Returns workflow run ID."""
    if not _TEMPORAL_AVAILABLE:
        logger.warning("temporalio not installed — workflow start skipped for task %s", task_id)
        return None

    import os
    from temporalio.client import Client

    temporal_host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    try:
        client = await Client.connect(temporal_host)
        handle = await client.start_workflow(
            VideoProductionWorkflow.run,
            task_id,
            id=f"video-production-{task_id}",
            task_queue="video-production",
        )
        logger.info("Started Temporal workflow %s for task %s", handle.id, task_id)
        return handle.id
    except Exception as exc:
        logger.error("Failed to start Temporal workflow for task %s: %s", task_id, exc)
        return None
