"""YouTube upload service (SA-43).

Uploads the final video to YouTube using the Data API v3 with:
  - Resumable upload for large files
  - Metadata: title, description, tags, category
  - Thumbnail: from task.script["selected_thumbnail_url"]
  - Privacy status: public (or unlisted for testing)

Returns the YouTube video ID on success, None on failure.
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.task import Task
from sqlalchemy import select

logger = logging.getLogger(__name__)

_YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
_YOUTUBE_THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
_DEFAULT_CATEGORY_ID = "22"  # People & Blogs


async def upload_to_youtube(task_id: str, privacy_status: str = "public") -> str | None:
    """
    Upload the task's final video to YouTube.

    Returns the YouTube video ID or None on failure.
    """
    settings = get_settings()
    if not settings.YOUTUBE_API_KEY:
        logger.warning("YOUTUBE_API_KEY not set — YouTube upload skipped")
        return None

    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if not row:
            return None

        script = row.script or {}
        final_url = row.final_video_url or script.get("final_video_url")
        if not final_url:
            logger.error("No final video URL for task %s", task_id)
            return None

        yt_meta = script.get("youtube_metadata", {})
        title = yt_meta.get("title") or row.title or "Untitled"
        description = yt_meta.get("description", "")
        tags = yt_meta.get("tags", [])
        thumbnail_url = script.get("selected_thumbnail_url")
        break

    try:
        import httpx
        from app.db.s3 import get_s3_client

        s3 = get_s3_client()
        bucket = settings.S3_BUCKET

        # Exchange API key for OAuth token is not possible — YouTube upload
        # requires OAuth 2.0. We use google-auth if GOOGLE_CLIENT_ID is set,
        # otherwise fall back to API key for metadata-only operations and log a warning.
        access_token = await _get_access_token(settings)
        if not access_token:
            logger.error("No OAuth access token available — YouTube upload requires OAuth 2.0")
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            # Download final video from S3
            key = final_url.split("//", 1)[1].split("/", 1)[1]
            local_path = os.path.join(tmpdir, "final.mp4")
            s3.download_file(bucket, key, local_path)
            file_size = os.path.getsize(local_path)

            # Initiate resumable upload
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(file_size),
            }
            body = {
                "snippet": {
                    "title": title[:100],
                    "description": description[:5000],
                    "tags": tags[:500],
                    "categoryId": _DEFAULT_CATEGORY_ID,
                },
                "status": {"privacyStatus": privacy_status},
            }

            async with httpx.AsyncClient(timeout=30) as client:
                init_resp = await client.post(
                    f"{_YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
                    headers=headers,
                    json=body,
                )
                init_resp.raise_for_status()
                upload_uri = init_resp.headers["Location"]

            # Upload file in chunks
            video_id = await _upload_file_chunked(upload_uri, local_path, access_token)

            if video_id and thumbnail_url:
                # Upload thumbnail
                await _upload_thumbnail(video_id, thumbnail_url, access_token, s3, bucket)

    except Exception as exc:
        logger.error("YouTube upload failed for task %s: %s", task_id, exc)
        return None

    # Persist video ID
    async for db in get_db():
        row = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
        if row:
            row.youtube_video_id = video_id
            row.status = "published"
            db.add(row)
            await db.commit()
        break

    logger.info("YouTube upload complete for task %s: video_id=%s", task_id, video_id)
    return video_id


async def _get_access_token(settings) -> str | None:
    """
    Return an OAuth 2.0 access token.

    Reads GOOGLE_OAUTH_REFRESH_TOKEN from environment; returns None if absent.
    The refresh token is obtained once via the OAuth consent flow and stored
    as an env var (outside the scope of this service).
    """
    refresh_token = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN", "")
    if not refresh_token:
        return None

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        return None

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]
    except Exception as exc:
        logger.error("Failed to refresh Google OAuth token: %s", exc)
        return None


async def _upload_file_chunked(
    upload_uri: str,
    file_path: str,
    access_token: str,
    chunk_size: int = 8 * 1024 * 1024,  # 8MB
) -> str | None:
    """Stream the file to YouTube's resumable upload URI. Returns video ID."""
    import httpx

    file_size = os.path.getsize(file_path)
    start = 0

    async with httpx.AsyncClient(timeout=300) as client:
        with open(file_path, "rb") as f:
            while start < file_size:
                chunk = f.read(chunk_size)
                end = start + len(chunk) - 1
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Type": "video/mp4",
                }
                resp = await client.put(upload_uri, content=chunk, headers=headers)
                if resp.status_code in (200, 201):
                    return resp.json().get("id")
                elif resp.status_code == 308:
                    # Resume Incomplete — continue
                    range_header = resp.headers.get("Range", f"bytes=0-{end}")
                    start = int(range_header.split("-")[1]) + 1
                else:
                    resp.raise_for_status()

    return None


async def _upload_thumbnail(
    video_id: str,
    thumbnail_s3_url: str,
    access_token: str,
    s3,
    bucket: str,
) -> None:
    """Upload thumbnail image to the YouTube video."""
    import httpx

    key = thumbnail_s3_url.split("//", 1)[1].split("/", 1)[1]
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        s3.download_file(bucket, key, tmp.name)
        with open(tmp.name, "rb") as f:
            img_data = f.read()
    os.unlink(tmp.name)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{_YOUTUBE_THUMBNAIL_URL}?videoId={video_id}",
            content=img_data,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "image/jpeg",
            },
        )
        resp.raise_for_status()
    logger.info("Thumbnail uploaded for video %s", video_id)
