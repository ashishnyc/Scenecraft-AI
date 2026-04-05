"""Cost tracker (SA-53).

Provides per-subtask API spend aggregation with daily/monthly budget alerts.

Features:
  - `record_cost(task_id, stage, amount, currency)` — atomic cost accumulation
  - `get_cost_breakdown(task_id)` — itemised cost by pipeline stage
  - `check_budget_alerts(workspace_id)` — emit warnings when spend exceeds thresholds
  - `get_workspace_spend_summary(workspace_id)` — daily/monthly totals for the UI

Stage keys match the pipeline stages:
  outline, audio_synthesis, clip_generation, music_generation, assembly,
  thumbnail_generation, youtube_upload
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.task import Task
from sqlalchemy import select, func

logger = logging.getLogger(__name__)

# Alert thresholds (configurable via env vars)
_DAILY_ALERT_USD = Decimal(os.environ.get("COST_ALERT_DAILY_USD", "25.00"))
_MONTHLY_ALERT_USD = Decimal(os.environ.get("COST_ALERT_MONTHLY_USD", "500.00"))
_SINGLE_TASK_ALERT_USD = Decimal(os.environ.get("COST_ALERT_TASK_USD", "10.00"))


@dataclass
class CostBreakdown:
    task_id: str
    total: Decimal = Decimal("0")
    by_stage: dict[str, Decimal] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "total_usd": str(self.total),
            "by_stage": {k: str(v) for k, v in self.by_stage.items()},
        }


async def record_cost(task_id: str, stage: str, amount: Decimal) -> None:
    """
    Record *amount* USD spent during *stage* for *task_id*.

    Atomically adds to task.total_cost_usd and appends a line-item to
    task.script["cost_breakdown"][stage].
    """
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            return

        row.total_cost_usd = (row.total_cost_usd or Decimal("0")) + amount

        sc = dict(row.script or {})
        breakdown = sc.get("cost_breakdown", {})
        existing = Decimal(str(breakdown.get(stage, "0")))
        breakdown[stage] = str(existing + amount)
        sc["cost_breakdown"] = breakdown
        row.script = sc

        db.add(row)
        await db.commit()
        break

    logger.debug("Cost recorded: task=%s stage=%s amount=$%s", task_id, stage, amount)


async def get_cost_breakdown(task_id: str) -> CostBreakdown:
    """Return itemised cost breakdown for a task."""
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            return CostBreakdown(task_id=task_id)

        sc = row.script or {}
        raw_breakdown = sc.get("cost_breakdown", {})
        by_stage = {k: Decimal(v) for k, v in raw_breakdown.items()}
        total = row.total_cost_usd or Decimal("0")

        return CostBreakdown(task_id=task_id, total=total, by_stage=by_stage)

    return CostBreakdown(task_id=task_id)


async def get_workspace_spend_summary(workspace_id: str) -> dict[str, Any]:
    """Return daily and monthly spend totals for a workspace."""
    from app.models.project import Project

    today = date.today()
    month_start = today.replace(day=1)

    async for db in get_db():
        projects = (await db.execute(
            select(Project).where(Project.workspace_id == workspace_id)
        )).scalars().all()
        project_ids = [str(p.id) for p in projects]

        daily_result = await db.execute(
            select(func.sum(Task.total_cost_usd))
            .where(
                Task.project_id.in_(project_ids),
                func.date(Task.updated_at) == today,
            )
        )
        monthly_result = await db.execute(
            select(func.sum(Task.total_cost_usd))
            .where(
                Task.project_id.in_(project_ids),
                func.date(Task.updated_at) >= month_start,
            )
        )
        daily_spend = daily_result.scalar() or Decimal("0")
        monthly_spend = monthly_result.scalar() or Decimal("0")
        break

    alerts = []
    if daily_spend >= _DAILY_ALERT_USD:
        alerts.append(f"Daily spend ${daily_spend:.2f} exceeds alert threshold ${_DAILY_ALERT_USD}")
    if monthly_spend >= _MONTHLY_ALERT_USD:
        alerts.append(f"Monthly spend ${monthly_spend:.2f} exceeds alert threshold ${_MONTHLY_ALERT_USD}")

    return {
        "workspace_id": workspace_id,
        "daily_spend_usd": str(daily_spend),
        "monthly_spend_usd": str(monthly_spend),
        "daily_alert_threshold_usd": str(_DAILY_ALERT_USD),
        "monthly_alert_threshold_usd": str(_MONTHLY_ALERT_USD),
        "alerts": alerts,
    }


async def check_task_cost_alert(task_id: str) -> list[str]:
    """Return list of alert messages if task cost exceeds threshold."""
    breakdown = await get_cost_breakdown(task_id)
    alerts = []
    if breakdown.total >= _SINGLE_TASK_ALERT_USD:
        alerts.append(
            f"Task {task_id} cost ${breakdown.total:.2f} exceeds single-task threshold ${_SINGLE_TASK_ALERT_USD}"
        )
        logger.warning("Cost alert: task %s = $%s", task_id, breakdown.total)
    return alerts
