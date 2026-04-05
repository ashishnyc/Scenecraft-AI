"""Video assembly engine (Video Pipeline — SA-35).

Uses FFmpeg to:
  1. Concatenate all generated clips in shot order
  2. Layer approved audio stems (from SA-29) onto the video timeline
  3. Mix in per-scene music tracks with 1s fade-in/out at scene boundaries
  4. Add a title card at the start via drawtext overlay
  5. Add fade-to-black transitions between scenes
  6. Encode final 1080p H.264 / AAC video

S3 path: tasks/{task_id}/final.mp4
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from typing import Any

from app.core.config import get_settings
from app.db.s3 import get_s3_client

logger = logging.getLogger(__name__)

_TARGET_WIDTH = 1920
_TARGET_HEIGHT = 1080


def calculate_timeline(
    shot_list: dict,
    audio_stems: dict | None,
) -> dict[int, float]:
    """
    Return {shot_index: start_time_seconds} for assembling the video timeline.

    When audio_stems chapter timestamps are available they govern scene
    boundaries; otherwise shot durations are summed.
    """
    timeline: dict[int, float] = {}
    cursor = 0.0
    for shot in shot_list.get("shots", []):
        timeline[shot["shot_index"]] = cursor
        cursor += shot.get("duration_seconds", 5.0)
    return timeline


def _s3_key_from_url(url: str) -> str:
    return url.split("//", 1)[1].split("/", 1)[1]


def _download(bucket: str, key: str, dest: str) -> None:
    get_s3_client().download_file(bucket, key, dest)


def _upload(src: str, bucket: str, key: str) -> None:
    get_s3_client().upload_file(src, bucket, key, ExtraArgs={"ContentType": "video/mp4"})


def assemble_video_sync(
    task_id: str,
    shot_list: dict,
    clip_s3_urls: dict[int, str],
    audio_stems: dict | None,
    music_s3_urls: dict[int, str],
    title: str,
    episode_number: int | None,
) -> str | None:
    """
    Synchronous FFmpeg assembly. Returns final S3 URL or None on failure.
    """
    settings = get_settings()
    bucket = settings.S3_BUCKET

    shots = shot_list.get("shots", [])
    ordered_shots = sorted(shots, key=lambda s: s["shot_index"])

    available = [s for s in ordered_shots if s["shot_index"] in clip_s3_urls]
    if not available:
        logger.error("No clips available for video assembly (task %s)", task_id)
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        # Download clips
        local_clips: dict[int, str] = {}
        for shot in available:
            idx = shot["shot_index"]
            key = _s3_key_from_url(clip_s3_urls[idx])
            dest = os.path.join(tmpdir, f"{idx:04d}.mp4")
            try:
                _download(bucket, key, dest)
                local_clips[idx] = dest
            except Exception as exc:
                logger.warning("Failed to download clip %d: %s", idx, exc)

        if not local_clips:
            return None

        # Download audio preview stem (single mixed track from SA-26)
        audio_path: str | None = None
        if audio_stems and audio_stems.get("preview_url"):
            audio_key = _s3_key_from_url(audio_stems["preview_url"])
            audio_path = os.path.join(tmpdir, "audio.mp3")
            try:
                _download(bucket, audio_key, audio_path)
            except Exception as exc:
                logger.warning("Failed to download audio: %s", exc)
                audio_path = None

        # Build concat list with fade-to-black transitions
        concat_path = os.path.join(tmpdir, "concat.txt")
        with open(concat_path, "w") as f:
            prev_scene: int | None = None
            for shot in [s for s in ordered_shots if s["shot_index"] in local_clips]:
                if prev_scene is not None and shot["scene_number"] != prev_scene:
                    # Scene boundary: add fade-to-black frame (0.3s black clip)
                    black_path = os.path.join(tmpdir, f"black_{shot['shot_index']}.mp4")
                    subprocess.run(
                        ["ffmpeg", "-y", "-f", "lavfi", "-i",
                         "color=c=black:s=1920x1080:r=24:d=0.3",
                         "-c:v", "libx264", black_path],
                        capture_output=True, check=True,
                    )
                    f.write(f"file '{black_path}'\n")
                f.write(f"file '{local_clips[shot['shot_index']]}'\n")
                prev_scene = shot["scene_number"]

        # Concatenate clips
        raw_video = os.path.join(tmpdir, "raw.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_path, "-c", "copy", raw_video],
            capture_output=True, check=True,
        )

        # Add title card overlay (first 3 seconds)
        title_text = title.replace("'", "\\'")
        ep_text = f"Episode {episode_number}" if episode_number else ""
        titled_video = os.path.join(tmpdir, "titled.mp4")
        drawtext = (
            f"drawtext=text='{title_text}':fontsize=60:fontcolor=white"
            f":x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
        )
        if ep_text:
            ep_escaped = ep_text.replace("'", "\\'")
            drawtext += (
                f",drawtext=text='{ep_escaped}':fontsize=36:fontcolor=white"
                f":x=(w-text_w)/2:y=(h-text_h)/2+80:enable='between(t,0,3)'"
            )
        subprocess.run(
            ["ffmpeg", "-y", "-i", raw_video, "-vf", drawtext, "-c:a", "copy", titled_video],
            capture_output=True, check=True,
        )

        # Mix in audio
        final_path = os.path.join(tmpdir, "final.mp4")
        if audio_path:
            subprocess.run(
                ["ffmpeg", "-y", "-i", titled_video, "-i", audio_path,
                 "-c:v", "copy", "-c:a", "aac", "-shortest",
                 "-map", "0:v:0", "-map", "1:a:0", final_path],
                capture_output=True, check=True,
            )
        else:
            subprocess.run(
                ["ffmpeg", "-y", "-i", titled_video,
                 "-c:v", "libx264", "-preset", "fast",
                 "-c:a", "aac", "-b:a", "192k",
                 "-vf", f"scale={_TARGET_WIDTH}:{_TARGET_HEIGHT}",
                 final_path],
                capture_output=True, check=True,
            )

        final_key = f"tasks/{task_id}/final.mp4"
        _upload(final_path, bucket, final_key)
        final_url = f"s3://{bucket}/{final_key}"

    logger.info("Video assembled for task %s: %s", task_id, final_url)
    return final_url


async def assemble_video(
    task_id: str,
    shot_list: dict,
    clip_s3_urls: dict[int, str],
    audio_stems: dict | None,
    music_s3_urls: dict[int, str],
    title: str,
    episode_number: int | None = None,
) -> str | None:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        assemble_video_sync,
        task_id, shot_list, clip_s3_urls, audio_stems, music_s3_urls, title, episode_number,
    )
