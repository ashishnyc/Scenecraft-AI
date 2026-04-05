"""GPU job scheduler (SA-49).

Routes video generation jobs to either:
  - Local GPU (if VRAM ≥ required and current load is low)
  - Cloud GPU (Kling / Runway / Replicate) otherwise

Decision logic:
  1. Query local GPU stats via nvidia-smi (if available)
  2. Estimate VRAM required for the job type
  3. Route local if: free_vram >= required AND local_queue_depth < MAX_LOCAL_QUEUE
  4. Otherwise route to the configured cloud provider

Cost model (approximate):
  - Local:  $0.005 / clip (electricity only)
  - Cloud:  $0.050 / clip (Kling API)

The scheduler also enforces a per-workspace daily spend cap.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_MAX_LOCAL_QUEUE = 4          # max concurrent local jobs
_LOCAL_VRAM_RESERVE_MB = 512  # headroom to leave free on local GPU

# VRAM required per job type (MB)
_VRAM_REQUIREMENTS: dict[str, int] = {
    "clip_generation": 8_000,   # Kling-equivalent local model
    "image_generation": 4_000,  # DALL-E-equivalent local model
    "audio_synthesis": 2_000,   # TTS local model
}

_LOCAL_COST_PER_CLIP = Decimal("0.005")
_CLOUD_COST_PER_CLIP = Decimal("0.050")


class JobRoute(str, Enum):
    local = "local"
    cloud = "cloud"


@dataclass
class RoutingDecision:
    route: JobRoute
    reason: str
    estimated_cost: Decimal
    gpu_info: dict[str, Any]


def _query_local_gpu() -> dict[str, Any]:
    """Return local GPU stats via nvidia-smi, or empty dict if unavailable."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.free,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {}
        lines = result.stdout.strip().splitlines()
        if not lines:
            return {}
        parts = [p.strip() for p in lines[0].split(",")]
        return {
            "name": parts[0],
            "free_mb": int(parts[1]),
            "total_mb": int(parts[2]),
            "utilization_pct": int(parts[3]),
        }
    except Exception:
        return {}


def _local_queue_depth() -> int:
    """Approximate queue depth by counting running ffmpeg/python inference processes."""
    try:
        result = subprocess.run(
            ["pgrep", "-c", "-f", "clip_generation"],
            capture_output=True, text=True,
        )
        return max(0, int(result.stdout.strip()) - 1)
    except Exception:
        return 0


def decide_route(job_type: str, num_jobs: int = 1) -> RoutingDecision:
    """
    Decide whether to run *num_jobs* jobs of *job_type* locally or in the cloud.

    Returns a RoutingDecision with the chosen route and cost estimate.
    """
    settings = get_settings()
    required_vram = _VRAM_REQUIREMENTS.get(job_type, 4_000)
    gpu = _query_local_gpu()
    queue_depth = _local_queue_depth()

    # Check local viability
    has_local_gpu = bool(gpu)
    enough_vram = gpu.get("free_mb", 0) >= required_vram + _LOCAL_VRAM_RESERVE_MB
    queue_ok = queue_depth < _MAX_LOCAL_QUEUE

    if has_local_gpu and enough_vram and queue_ok:
        cost = _LOCAL_COST_PER_CLIP * num_jobs
        return RoutingDecision(
            route=JobRoute.local,
            reason=f"Local GPU '{gpu.get('name')}' has {gpu.get('free_mb')}MB free (need {required_vram}MB)",
            estimated_cost=cost,
            gpu_info=gpu,
        )

    # Route to cloud
    if not has_local_gpu:
        reason = "No local GPU detected"
    elif not enough_vram:
        reason = f"Insufficient VRAM: {gpu.get('free_mb', 0)}MB free < {required_vram + _LOCAL_VRAM_RESERVE_MB}MB needed"
    else:
        reason = f"Local queue full ({queue_depth}/{_MAX_LOCAL_QUEUE} jobs)"

    cost = _CLOUD_COST_PER_CLIP * num_jobs
    return RoutingDecision(
        route=JobRoute.cloud,
        reason=reason,
        estimated_cost=cost,
        gpu_info=gpu,
    )


async def check_daily_spend_cap(workspace_id: str, estimated_cost: Decimal) -> bool:
    """
    Return True if adding estimated_cost stays within the daily spend cap.

    Cap is $50/day per workspace by default (configurable via DAILY_SPEND_CAP_USD env var).
    """
    import os
    from app.db.postgres import get_db
    from app.models.task import Task
    from app.models.project import Project
    from sqlalchemy import select, func
    from datetime import date

    cap = Decimal(os.environ.get("DAILY_SPEND_CAP_USD", "50.00"))

    async for db in get_db():
        # Sum today's costs across all tasks in the workspace
        today = date.today()
        result = await db.execute(
            select(func.sum(Task.total_cost_usd))
            .join(Project, Task.project_id == Project.id)
            .where(
                Project.workspace_id == workspace_id,
                func.date(Task.created_at) == today,
            )
        )
        today_spend = result.scalar() or Decimal("0")
        break

    if today_spend + estimated_cost > cap:
        logger.warning(
            "Daily spend cap ($%s) would be exceeded: today=$%s + new=$%s",
            cap, today_spend, estimated_cost,
        )
        return False
    return True


def route_clip_generation(task_id: str, num_clips: int) -> RoutingDecision:
    """Convenience wrapper for clip generation routing."""
    decision = decide_route("clip_generation", num_clips)
    logger.info(
        "Routing %d clips for task %s → %s (%s), est. cost $%s",
        num_clips, task_id, decision.route.value, decision.reason, decision.estimated_cost,
    )
    return decision
