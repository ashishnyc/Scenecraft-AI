"""Asset lifecycle manager (SA-51).

Manages S3 storage for task assets:
  - Archives intermediate files (clips, stems, environments) after 30 days
  - Permanently retains final.mp4 and thumbnails
  - Deletes archived files after 90 days (configurable)
  - Moves assets to S3 Glacier (or S3 IA) storage class on archive

Archive policy:
  tasks/{task_id}/clips/           → archive after 30d, delete after 90d
  tasks/{task_id}/audio/stems/     → archive after 30d, delete after 90d
  tasks/{task_id}/hls/             → delete after 30d (regenerable)
  tasks/{task_id}/thumbnails/      → retain (small, needed for published card)
  tasks/{task_id}/final.mp4        → retain permanently
  projects/{project_id}/environments/ → archive after 90d (shared, expensive to regen)

This is scheduled daily at 02:00 UTC by APScheduler.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.task import Task
from sqlalchemy import select

logger = logging.getLogger(__name__)

_ARCHIVE_AFTER_DAYS = 30
_DELETE_AFTER_DAYS = 90
_HLS_DELETE_AFTER_DAYS = 30

# S3 storage classes
_GLACIER_IR = "GLACIER_IR"   # Glacier Instant Retrieval
_STANDARD_IA = "STANDARD_IA"


def _days_since(dt: datetime) -> int:
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


async def _list_prefix(s3, bucket: str, prefix: str) -> list[dict]:
    """List all objects under prefix, returning [{Key, LastModified, StorageClass}]."""
    objects = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            objects.append(obj)
    return objects


async def archive_task_assets(task_id: str) -> dict[str, Any]:
    """
    Apply lifecycle policy to all assets for a single task.

    Returns summary: {"archived": n, "deleted": n, "retained": n}
    """
    settings = get_settings()
    from app.db.s3 import get_s3_client
    s3 = get_s3_client()
    bucket = settings.S3_BUCKET

    archived = deleted = retained = 0

    prefixes_to_archive = [
        f"tasks/{task_id}/clips/",
        f"tasks/{task_id}/audio/stems/",
    ]
    prefixes_to_delete_hls = [f"tasks/{task_id}/hls/"]
    prefixes_to_retain = [
        f"tasks/{task_id}/final.mp4",
        f"tasks/{task_id}/thumbnails/",
    ]

    # Archive intermediate assets
    for prefix in prefixes_to_archive:
        try:
            objects = await _list_prefix(s3, bucket, prefix)
            for obj in objects:
                age = _days_since(obj["LastModified"])
                storage_class = obj.get("StorageClass", "STANDARD")

                if age >= _DELETE_AFTER_DAYS:
                    s3.delete_object(Bucket=bucket, Key=obj["Key"])
                    deleted += 1
                    logger.debug("Deleted %s (age=%dd)", obj["Key"], age)
                elif age >= _ARCHIVE_AFTER_DAYS and storage_class == "STANDARD":
                    # Move to Glacier Instant Retrieval
                    s3.copy_object(
                        Bucket=bucket,
                        CopySource={"Bucket": bucket, "Key": obj["Key"]},
                        Key=obj["Key"],
                        StorageClass=_GLACIER_IR,
                        MetadataDirective="COPY",
                    )
                    archived += 1
                    logger.debug("Archived %s to %s (age=%dd)", obj["Key"], _GLACIER_IR, age)
                else:
                    retained += 1
        except Exception as exc:
            logger.warning("Asset lifecycle failed for prefix %s: %s", prefix, exc)

    # Delete HLS segments after 30 days (they can be regenerated on demand)
    for prefix in prefixes_to_delete_hls:
        try:
            objects = await _list_prefix(s3, bucket, prefix)
            for obj in objects:
                age = _days_since(obj["LastModified"])
                if age >= _HLS_DELETE_AFTER_DAYS:
                    s3.delete_object(Bucket=bucket, Key=obj["Key"])
                    deleted += 1
                else:
                    retained += 1
        except Exception as exc:
            logger.warning("HLS cleanup failed for prefix %s: %s", prefix, exc)

    logger.info(
        "Asset lifecycle for task %s: archived=%d deleted=%d retained=%d",
        task_id, archived, deleted, retained,
    )
    return {"task_id": task_id, "archived": archived, "deleted": deleted, "retained": retained}


async def run_lifecycle_for_all_tasks() -> dict[str, Any]:
    """Run lifecycle management across all tasks. Called by APScheduler."""
    total_archived = total_deleted = total_retained = 0
    processed = 0

    async for db in get_db():
        # Only process published or final_review tasks (pipeline complete)
        rows = (await db.execute(
            select(Task).where(Task.status.in_(["published", "scheduled"]))
        )).scalars().all()

        for row in rows:
            try:
                result = await archive_task_assets(str(row.id))
                total_archived += result["archived"]
                total_deleted += result["deleted"]
                total_retained += result["retained"]
                processed += 1
            except Exception as exc:
                logger.error("Lifecycle failed for task %s: %s", row.id, exc)
        break

    logger.info(
        "Lifecycle run complete: %d tasks processed, %d archived, %d deleted",
        processed, total_archived, total_deleted,
    )
    return {
        "processed": processed,
        "archived": total_archived,
        "deleted": total_deleted,
        "retained": total_retained,
    }


async def archive_old_environments(project_id: str) -> int:
    """Archive environment background plates older than 90 days."""
    settings = get_settings()
    from app.db.s3 import get_s3_client
    s3 = get_s3_client()
    bucket = settings.S3_BUCKET
    prefix = f"projects/{project_id}/environments/"
    archived = 0

    try:
        objects = await _list_prefix(s3, bucket, prefix)
        for obj in objects:
            age = _days_since(obj["LastModified"])
            if age >= 90 and obj.get("StorageClass", "STANDARD") == "STANDARD":
                s3.copy_object(
                    Bucket=bucket,
                    CopySource={"Bucket": bucket, "Key": obj["Key"]},
                    Key=obj["Key"],
                    StorageClass=_STANDARD_IA,
                    MetadataDirective="COPY",
                )
                archived += 1
    except Exception as exc:
        logger.warning("Environment archive failed for project %s: %s", project_id, exc)

    return archived
