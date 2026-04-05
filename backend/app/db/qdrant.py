"""Qdrant vector database client and collection management."""
from __future__ import annotations

import logging
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.core.config import get_settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "youtube_videos"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 (fastembed default)


@lru_cache(maxsize=1)
def get_qdrant_client() -> AsyncQdrantClient:
    settings = get_settings()
    if settings.QDRANT_URL:
        return AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    # In-memory for local dev / tests
    return AsyncQdrantClient(":memory:")


async def ensure_collection(client: AsyncQdrantClient) -> None:
    """Create the youtube_videos collection if it doesn't exist."""
    existing = await client.get_collections()
    names = [c.name for c in existing.collections]
    if COLLECTION_NAME not in names:
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s'", COLLECTION_NAME)
