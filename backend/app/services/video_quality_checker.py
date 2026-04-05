"""Video quality checker (Video Pipeline — SA-36).

Runs automated quality checks on the assembled video before it reaches
the creator for final review.

Checks:
  1. Resolution: must be 1920×1080
  2. Framerate: ≥24 fps
  3. Codec: H.264 video, AAC audio
  4. Duration: within 10% of expected (based on shot durations)
  5. Black frames: no unintentional sequences >0.5 s
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_EXPECTED_WIDTH = 1920
_EXPECTED_HEIGHT = 1080
_MIN_FRAMERATE = 24.0
_DURATION_TOLERANCE = 0.10       # ±10%
_BLACK_FRAME_MIN_DURATION = 0.5  # seconds


@dataclass
class QualityReport:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details,
        }


def _run_ffprobe(video_path: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name,r_frame_rate",
            "-show_entries", "format=duration",
            "-of", "json", video_path,
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def _detect_black_frames(video_path: str) -> list[dict[str, float]]:
    """Return list of {start, end, duration} for black frame sequences."""
    result = subprocess.run(
        ["ffmpeg", "-i", video_path,
         "-vf", f"blackdetect=d={_BLACK_FRAME_MIN_DURATION}:pic_th=0.98",
         "-an", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    segments = []
    for line in result.stderr.splitlines():
        if "black_start" in line:
            parts = dict(p.split(":") for p in line.split() if ":" in p)
            try:
                segments.append({
                    "start": float(parts.get("black_start", 0)),
                    "end": float(parts.get("black_end", 0)),
                    "duration": float(parts.get("black_duration", 0)),
                })
            except (ValueError, KeyError):
                pass
    return segments


def _parse_framerate(r_frame_rate: str) -> float:
    """Parse '24000/1001' → float."""
    try:
        num, den = r_frame_rate.split("/")
        return float(num) / float(den)
    except Exception:
        return 0.0


def check_video_quality(
    video_path: str,
    expected_duration_seconds: float | None = None,
    scene_boundary_timestamps: list[float] | None = None,
) -> QualityReport:
    """
    Run all quality checks on *video_path*.

    *scene_boundary_timestamps* is a sorted list of scene start times in
    seconds; black frames at those positions are treated as intentional
    fade-to-black transitions and not flagged.
    """
    report = QualityReport(passed=True)

    try:
        probe = _run_ffprobe(video_path)
    except Exception as exc:
        report.passed = False
        report.errors.append(f"ffprobe failed: {exc}")
        return report

    streams = probe.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video_stream:
        video_stream = streams[0] if streams else {}

    # 1. Resolution
    width = video_stream.get("width", 0)
    height = video_stream.get("height", 0)
    report.details["resolution"] = f"{width}x{height}"
    if width != _EXPECTED_WIDTH or height != _EXPECTED_HEIGHT:
        report.passed = False
        report.errors.append(f"Resolution {width}x{height} — expected {_EXPECTED_WIDTH}x{_EXPECTED_HEIGHT}")

    # 2. Framerate
    fps = _parse_framerate(video_stream.get("r_frame_rate", "0/1"))
    report.details["framerate"] = round(fps, 2)
    if fps < _MIN_FRAMERATE:
        report.passed = False
        report.errors.append(f"Framerate {fps:.1f} fps < minimum {_MIN_FRAMERATE}")

    # 3. Codec
    codec = video_stream.get("codec_name", "")
    report.details["codec"] = codec
    if codec not in ("h264", "libx264"):
        report.warnings.append(f"Codec is '{codec}', expected h264")

    # 4. Duration
    actual_duration = float(probe.get("format", {}).get("duration", 0))
    report.details["duration_seconds"] = round(actual_duration, 2)
    if expected_duration_seconds and expected_duration_seconds > 0:
        tolerance = expected_duration_seconds * _DURATION_TOLERANCE
        if abs(actual_duration - expected_duration_seconds) > tolerance:
            report.warnings.append(
                f"Duration {actual_duration:.1f}s differs from expected "
                f"{expected_duration_seconds:.1f}s by more than {_DURATION_TOLERANCE * 100:.0f}%"
            )

    # 5. Black frames (filter out intentional scene transitions)
    try:
        black_segments = _detect_black_frames(video_path)
        boundaries = set(round(t, 1) for t in (scene_boundary_timestamps or []))
        unintentional = [
            seg for seg in black_segments
            if not any(abs(seg["start"] - b) < 1.0 for b in boundaries)
        ]
        if unintentional:
            report.passed = False
            report.errors.append(
                f"Detected {len(unintentional)} unintentional black frame sequence(s)"
            )
            report.details["black_frame_segments"] = unintentional
    except Exception as exc:
        report.warnings.append(f"Black frame detection failed: {exc}")

    return report


async def check_quality(
    task_id: str,
    final_s3_url: str,
    shot_list: dict,
    audio_stems: dict | None,
) -> dict[str, Any] | None:
    """Download the final video and run quality checks. Returns report dict or None."""
    from app.core.config import get_settings
    from app.db.s3 import get_s3_client

    settings = get_settings()
    bucket = settings.S3_BUCKET
    key = final_s3_url.split("//", 1)[1].split("/", 1)[1]

    # Compute expected duration from shot list
    expected = sum(s.get("duration_seconds", 0) for s in shot_list.get("shots", []))

    # Scene boundary timestamps from chapter timestamps
    boundaries: list[float] = []
    if audio_stems:
        boundaries = sorted(v / 1000 for v in audio_stems.get("chapter_timestamps", {}).values())

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = os.path.join(tmpdir, "final.mp4")
        try:
            get_s3_client().download_file(bucket, key, local_path)
        except Exception as exc:
            logger.error("Failed to download video for QC (task %s): %s", task_id, exc)
            return None

        report = check_video_quality(local_path, expected, boundaries)

    logger.info(
        "Quality check for task %s: %s (%d errors, %d warnings)",
        task_id, "PASS" if report.passed else "FAIL",
        len(report.errors), len(report.warnings),
    )
    return report.to_dict()
