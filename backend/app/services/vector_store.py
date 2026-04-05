"""Embedding generation and Qdrant upsert/search operations."""
from __future__ import annotations

import logging
from typing import Any

from qdrant_client.models import PointStruct, ScoredPoint

from app.db.qdrant import COLLECTION_NAME, ensure_collection, get_qdrant_client

logger = logging.getLogger(__name__)

_embedder = None


def _get_embedder():
    """Lazy-load fastembed model (cached after first call)."""
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embedder


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return a list of embedding vectors for the given texts."""
    embedder = _get_embedder()
    return [list(vec) for vec in embedder.embed(texts)]


async def upsert_videos(videos: list[dict[str, Any]]) -> int:
    """
    Upsert video embeddings into Qdrant.
    Each dict must have: video_id, title, description (optional), workspace_id.
    Returns count of upserted points.
    """
    if not videos:
        return 0

    client = get_qdrant_client()
    await ensure_collection(client)

    texts = [f"{v['title']} {v.get('description', '') or ''}".strip() for v in videos]
    vectors = embed_texts(texts)

    points = [
        PointStruct(
            id=_stable_id(v["video_id"]),
            vector=vec,
            payload={
                "video_id": v["video_id"],
                "title": v["title"],
                "workspace_id": str(v["workspace_id"]),
                "channel_id": v.get("channel_id", ""),
            },
        )
        for v, vec in zip(videos, vectors)
    ]

    await client.upsert(collection_name=COLLECTION_NAME, points=points)
    return len(points)


async def search_similar(
    text: str,
    workspace_id: str,
    limit: int = 5,
) -> list[ScoredPoint]:
    """
    Find the most similar videos to the given text in the workspace's index.
    Returns a list of ScoredPoint (each has .score and .payload).
    """
    client = get_qdrant_client()
    await ensure_collection(client)

    from qdrant_client.models import Filter, FieldCondition, MatchValue
    vector = embed_texts([text])[0]

    response = await client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        query_filter=Filter(
            must=[FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id))]
        ),
        limit=limit,
        with_payload=True,
    )
    return response.points


def _stable_id(video_id: str) -> int:
    """Convert a YouTube video ID string to a stable int for Qdrant point IDs."""
    return abs(hash(video_id)) % (2**53)
