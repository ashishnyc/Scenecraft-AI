"""Check pitch originality against the Qdrant index of existing YouTube videos."""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.services.vector_store import search_similar

logger = logging.getLogger(__name__)


def compute_originality_score(max_similarity: float) -> float:
    """
    Convert max cosine similarity to an originality score (0-1).
    originality = 1 - max_similarity  (higher is more original)
    """
    return round(1.0 - max(0.0, min(1.0, max_similarity)), 4)


def is_low_originality(max_similarity: float, threshold: float | None = None) -> bool:
    """Return True if the pitch is too similar to existing content."""
    if threshold is None:
        threshold = get_settings().ORIGINALITY_THRESHOLD
    return max_similarity >= threshold


async def check_pitch_originality(
    pitch_text: str,
    workspace_id: str,
) -> dict[str, Any]:
    """
    Search Qdrant for similar videos and return originality metadata.

    Returns:
        {
            "originality_score": float,       # 0 = copy, 1 = fully original
            "max_similarity": float,
            "low_originality": bool,
            "similar_videos": [{"title": ..., "video_id": ..., "score": ...}]
        }
    """
    try:
        results = await search_similar(pitch_text, workspace_id, limit=5)
    except Exception as exc:
        logger.warning("Qdrant search failed: %s — assuming original", exc)
        return {
            "originality_score": 1.0,
            "max_similarity": 0.0,
            "low_originality": False,
            "similar_videos": [],
        }

    if not results:
        return {
            "originality_score": 1.0,
            "max_similarity": 0.0,
            "low_originality": False,
            "similar_videos": [],
        }

    max_similarity = max(r.score for r in results)
    similar_videos = [
        {
            "title": r.payload.get("title", ""),
            "video_id": r.payload.get("video_id", ""),
            "score": round(r.score, 4),
        }
        for r in results
    ]

    return {
        "originality_score": compute_originality_score(max_similarity),
        "max_similarity": round(max_similarity, 4),
        "low_originality": is_low_originality(max_similarity),
        "similar_videos": similar_videos,
    }
