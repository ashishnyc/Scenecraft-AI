"""Audio streaming endpoint — serves S3 audio files to the browser."""
from __future__ import annotations

import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.db.s3 import get_s3_client

router = APIRouter(tags=["audio"])


@router.get("/audio/stream/{s3_key:path}")
async def stream_audio(
    s3_key: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Stream an S3 audio file (MP3) to the browser.

    *s3_key* is the URL-encoded S3 object key, e.g.
    ``tasks%2F{id}%2Faudio%2Fpreview.mp3``.
    """
    key = urllib.parse.unquote(s3_key)
    settings = get_settings()

    # Security: key must be under tasks/ prefix to prevent path traversal
    if not key.startswith("tasks/"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        s3 = get_s3_client()
        obj = s3.get_object(Bucket=settings.S3_BUCKET, Key=key)
        body = obj["Body"]
        content_length = obj.get("ContentLength")

        headers = {"Accept-Ranges": "bytes"}
        if content_length:
            headers["Content-Length"] = str(content_length)

        return StreamingResponse(
            body.iter_chunks(chunk_size=65536),
            media_type="audio/mpeg",
            headers=headers,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found",
        ) from exc
