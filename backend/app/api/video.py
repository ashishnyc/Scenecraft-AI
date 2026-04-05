"""Video endpoints — SA-37: HLS preview, SA-39: thumbnail selector, SA-40: metadata editor, SA-45: analytics."""
from __future__ import annotations

import os
import subprocess
import tempfile
import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.db.s3 import get_s3_client

router = APIRouter(tags=["video"])


# ── SA-37: HLS Preview ────────────────────────────────────────────────────────

@router.post("/tasks/{task_id}/video/hls-preview")
async def create_hls_preview(
    task_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """
    Transcode the task's final.mp4 to HLS segments and upload to S3.

    Returns ``{"master_url": "s3://...", "signed_url": "https://..."}``
    """
    settings = get_settings()
    bucket = settings.S3_BUCKET
    s3 = get_s3_client()

    src_key = f"tasks/{task_id}/final.mp4"
    hls_prefix = f"tasks/{task_id}/hls"
    master_key = f"{hls_prefix}/master.m3u8"

    # Check if HLS already exists
    try:
        s3.head_object(Bucket=bucket, Key=master_key)
        signed = s3.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": master_key}, ExpiresIn=3600
        )
        return {"master_url": f"s3://{bucket}/{master_key}", "signed_url": signed}
    except Exception:
        pass  # Need to transcode

    with tempfile.TemporaryDirectory() as tmpdir:
        local_src = os.path.join(tmpdir, "final.mp4")
        try:
            s3.download_file(bucket, src_key, local_src)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"final.mp4 not found for task {task_id}: {exc}",
            )

        hls_dir = os.path.join(tmpdir, "hls")
        os.makedirs(hls_dir)
        master_local = os.path.join(hls_dir, "master.m3u8")

        # Two-rendition HLS: 1080p and 480p
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", local_src,
                # 1080p stream
                "-map", "0:v:0", "-map", "0:a:0",
                "-c:v:0", "libx264", "-preset", "fast", "-crf", "23",
                "-s:v:0", "1920x1080", "-b:v:0", "4000k",
                "-c:a:0", "aac", "-b:a:0", "192k",
                # 480p stream
                "-map", "0:v:0", "-map", "0:a:0",
                "-c:v:1", "libx264", "-preset", "fast", "-crf", "28",
                "-s:v:1", "854x480", "-b:v:1", "1200k",
                "-c:a:1", "aac", "-b:a:1", "128k",
                # HLS output
                "-f", "hls",
                "-hls_time", "6",
                "-hls_playlist_type", "vod",
                "-hls_segment_filename", os.path.join(hls_dir, "seg_%v_%03d.ts"),
                "-master_pl_name", "master.m3u8",
                "-var_stream_map", "v:0,a:0 v:1,a:1",
                os.path.join(hls_dir, "stream_%v.m3u8"),
            ],
            capture_output=True, check=True,
        )

        # Upload all HLS files to S3
        for fname in os.listdir(hls_dir):
            local_file = os.path.join(hls_dir, fname)
            s3_key = f"{hls_prefix}/{fname}"
            content_type = (
                "application/x-mpegURL" if fname.endswith(".m3u8") else "video/MP2T"
            )
            s3.upload_file(
                local_file, bucket, s3_key,
                ExtraArgs={"ContentType": content_type},
            )

    signed = s3.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": master_key}, ExpiresIn=3600
    )
    return {"master_url": f"s3://{bucket}/{master_key}", "signed_url": signed}


@router.get("/tasks/{task_id}/video/hls-segment/{segment_key:path}")
async def stream_hls_segment(
    task_id: str,
    segment_key: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Stream an HLS segment or playlist file from S3."""
    settings = get_settings()
    key = f"tasks/{task_id}/hls/{urllib.parse.unquote(segment_key)}"

    # Security: ensure key stays within task's hls/ prefix
    if not key.startswith(f"tasks/{task_id}/hls/"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        s3 = get_s3_client()
        obj = s3.get_object(Bucket=settings.S3_BUCKET, Key=key)
        body = obj["Body"]
        content_type = (
            "application/x-mpegURL" if key.endswith(".m3u8") else "video/MP2T"
        )
        return StreamingResponse(body.iter_chunks(chunk_size=65536), media_type=content_type)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found") from exc


# ── SA-38: Video review helpers ───────────────────────────────────────────────

@router.get("/tasks/{task_id}/video/review-data")
async def get_video_review_data(
    task_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Return shot list, quality report, cost, and presigned HLS URL for the review UI."""
    from app.db.postgres import get_db
    from app.models.task import Task
    from sqlalchemy import select

    settings = get_settings()
    s3 = get_s3_client()
    bucket = settings.S3_BUCKET

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        script = row.script or {}
        shot_list = script.get("shot_list", {})
        quality_report = script.get("quality_report", {})
        total_cost = str(row.total_cost_usd) if row.total_cost_usd else "0.00"

        # Presigned master playlist
        master_key = f"tasks/{task_id}/hls/master.m3u8"
        hls_signed_url = None
        try:
            hls_signed_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": master_key},
                ExpiresIn=3600,
            )
        except Exception:
            pass

        return {
            "task_id": task_id,
            "title": row.title,
            "status": row.status,
            "shot_list": shot_list,
            "quality_report": quality_report,
            "total_cost_usd": total_cost,
            "hls_signed_url": hls_signed_url,
        }

    raise HTTPException(status_code=500, detail="DB error")


class VideoFeedbackRequest(BaseModel):
    action: str  # "approve" | "request_changes"
    notes: str = ""
    flagged_shot_indices: list[int] = []


@router.post("/tasks/{task_id}/video/feedback")
async def submit_video_feedback(
    task_id: str,
    body: VideoFeedbackRequest,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Submit Gate 2 review feedback (approve or request changes)."""
    from app.db.postgres import get_db
    from app.models.task import Task
    from app.api.tasks import validate_transition
    from sqlalchemy import select

    if body.action not in ("approve", "request_changes"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'request_changes'")

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        script = dict(row.script or {})

        if body.action == "approve":
            new_status = "scheduled"
            validate_transition(row.status, new_status)
            row.status = new_status
            script["video_review"] = {"approved": True, "notes": body.notes}
        else:
            # request_changes: go back to producing for re-generation
            new_status = "producing"
            script["video_review"] = {
                "approved": False,
                "notes": body.notes,
                "flagged_shot_indices": body.flagged_shot_indices,
            }
            row.status = new_status

        row.script = script
        db.add(row)
        await db.commit()
        return {"task_id": task_id, "status": row.status, "action": body.action}

    raise HTTPException(status_code=500, detail="DB error")


# ── SA-39: Thumbnail Selector ─────────────────────────────────────────────────

@router.post("/tasks/{task_id}/thumbnails/generate")
async def generate_thumbnails(
    task_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Generate 5 AI thumbnail options and store presigned URLs."""
    import asyncio
    from app.services.thumbnail_generator import generate_thumbnail_options

    options = await generate_thumbnail_options(task_id)
    if options is None:
        raise HTTPException(status_code=503, detail="Thumbnail generation failed")
    return {"task_id": task_id, "options": options}


@router.post("/tasks/{task_id}/thumbnails/select")
async def select_thumbnail(
    task_id: str,
    body: dict,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Select a thumbnail (by index) or upload a custom one (base64 in body)."""
    from app.db.postgres import get_db
    from app.models.task import Task
    from sqlalchemy import select
    import base64

    settings = get_settings()
    s3 = get_s3_client()
    bucket = settings.S3_BUCKET

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        script = dict(row.script or {})

        if "custom_image_b64" in body:
            # Upload custom thumbnail
            img_data = base64.b64decode(body["custom_image_b64"])
            key = f"tasks/{task_id}/thumbnail_custom.jpg"
            s3.put_object(
                Bucket=bucket, Key=key, Body=img_data,
                ContentType="image/jpeg",
            )
            thumbnail_url = f"s3://{bucket}/{key}"
        elif "option_index" in body:
            options = script.get("thumbnail_options", [])
            idx = int(body["option_index"])
            if idx < 0 or idx >= len(options):
                raise HTTPException(status_code=400, detail="Invalid option_index")
            thumbnail_url = options[idx]["s3_url"]
        else:
            raise HTTPException(status_code=400, detail="Provide option_index or custom_image_b64")

        script["selected_thumbnail_url"] = thumbnail_url
        row.script = script
        db.add(row)
        await db.commit()
        return {"task_id": task_id, "thumbnail_url": thumbnail_url}

    raise HTTPException(status_code=500, detail="DB error")


# ── SA-40: Title / Description / Tags Editor ──────────────────────────────────

@router.post("/tasks/{task_id}/metadata/generate")
async def generate_metadata(
    task_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """LLM-pre-fill YouTube title, description, and tags."""
    from app.services.metadata_generator import generate_youtube_metadata

    result = await generate_youtube_metadata(task_id)
    if result is None:
        raise HTTPException(status_code=503, detail="Metadata generation failed")
    return result


class MetadataSaveRequest(BaseModel):
    title: str
    description: str
    tags: list[str]
    scheduled_at: str | None = None  # ISO-8601


@router.put("/tasks/{task_id}/metadata")
async def save_metadata(
    task_id: str,
    body: MetadataSaveRequest,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Persist edited YouTube metadata to task.script."""
    from app.db.postgres import get_db
    from app.models.task import Task
    from sqlalchemy import select

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        script = dict(row.script or {})
        script["youtube_metadata"] = {
            "title": body.title,
            "description": body.description,
            "tags": body.tags,
            "scheduled_at": body.scheduled_at,
        }
        row.title = body.title  # keep task title in sync
        row.script = script
        db.add(row)
        await db.commit()
        return {"task_id": task_id, "youtube_metadata": script["youtube_metadata"]}

    raise HTTPException(status_code=500, detail="DB error")


# ── SA-45: Analytics endpoints ────────────────────────────────────────────────

@router.get("/tasks/{task_id}/analytics")
async def get_task_analytics(
    task_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Return performance metrics + computed retention curve for a published task."""
    from app.db.postgres import get_db as _get_db
    from app.models.task import Task as _Task
    from app.services.analytics_tracker import compute_retention_curve
    from sqlalchemy import select as _select

    async for db in _get_db():
        row = (await db.execute(_select(_Task).where(_Task.id == task_id))).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        metrics = row.performance_metrics or {}
        return {
            "task_id": task_id,
            "youtube_video_id": row.youtube_video_id,
            "latest": metrics.get("latest", {}),
            "retention_curve": compute_retention_curve(metrics),
            "total_cost_usd": str(row.total_cost_usd or "0.00"),
        }

    raise HTTPException(status_code=500, detail="DB error")


@router.post("/tasks/{task_id}/analytics/poll")
async def poll_analytics_now(
    task_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Force an immediate analytics poll for a task."""
    from app.services.analytics_tracker import poll_video_analytics
    snapshot = await poll_video_analytics(task_id)
    if snapshot is None:
        raise HTTPException(status_code=503, detail="Analytics poll failed or video not published")
    return {"task_id": task_id, "snapshot": snapshot}


@router.get("/workspaces/{workspace_id}/analytics/summary")
async def get_workspace_analytics_summary(
    workspace_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Aggregate analytics across all published tasks in a workspace."""
    from app.db.postgres import get_db as _get_db
    from app.models.task import Task as _Task
    from app.models.project import Project as _Project
    from sqlalchemy import select as _select

    async for db in _get_db():
        projects = (await db.execute(
            _select(_Project).where(_Project.workspace_id == workspace_id)
        )).scalars().all()
        project_ids = [str(p.id) for p in projects]

        tasks = (await db.execute(
            _select(_Task).where(
                _Task.project_id.in_(project_ids),
                _Task.status == "published",
            )
        )).scalars().all()

        total_views = 0
        total_likes = 0
        total_cost = 0.0
        per_video = []

        for t in tasks:
            metrics = t.performance_metrics or {}
            latest = metrics.get("latest", {})
            views = latest.get("views", 0)
            likes = latest.get("likes", 0)
            total_views += views
            total_likes += likes
            total_cost += float(t.total_cost_usd or 0)
            per_video.append({
                "task_id": str(t.id),
                "title": t.title,
                "youtube_video_id": t.youtube_video_id,
                "views": views,
                "likes": likes,
                "cost_usd": str(t.total_cost_usd or "0.00"),
            })

        return {
            "workspace_id": workspace_id,
            "published_count": len(tasks),
            "total_views": total_views,
            "total_likes": total_likes,
            "total_cost_usd": round(total_cost, 4),
            "videos": sorted(per_video, key=lambda x: x["views"], reverse=True),
        }

    raise HTTPException(status_code=500, detail="DB error")
