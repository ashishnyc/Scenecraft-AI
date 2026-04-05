"""Performance optimisations (SA-55).

Three areas:
  1. DB query tuning — connection pool sizing, query result caching via Redis
  2. Caching strategy — Redis TTL cache decorator for expensive read endpoints
  3. CDN config — S3 presigned URL caching, static asset cache headers

Usage:
  @cached(ttl=300, key_prefix="workspace_summary")
  async def expensive_endpoint(...): ...
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── 1. Optimised DB engine settings ──────────────────────────────────────────

DB_POOL_SETTINGS = {
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30,
    "pool_recycle": 1800,   # recycle connections every 30 min
    "pool_pre_ping": True,
}

# ── 2. Redis cache decorator ──────────────────────────────────────────────────

_CACHE_TTL_DEFAULT = 300  # 5 minutes


def _make_cache_key(prefix: str, args: tuple, kwargs: dict) -> str:
    raw = json.dumps({"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in kwargs.items()}},
                     sort_keys=True)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"cache:{prefix}:{digest}"


def cached(ttl: int = _CACHE_TTL_DEFAULT, key_prefix: str = ""):
    """
    Async cache decorator backed by Redis.

    Caches the JSON-serialisable return value for *ttl* seconds.
    Cache is bypassed (and result stored fresh) on any Redis error.

    Example::

        @cached(ttl=60, key_prefix="workspace_summary")
        async def get_workspace_summary(workspace_id: str) -> dict: ...
    """
    def decorator(fn: Callable):
        prefix = key_prefix or fn.__qualname__

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            key = _make_cache_key(prefix, args, kwargs)
            try:
                from app.db.redis import get_redis
                redis = get_redis()
                cached_val = await redis.get(key)
                if cached_val:
                    logger.debug("Cache hit: %s", key)
                    return json.loads(cached_val)
            except Exception as exc:
                logger.debug("Cache read failed (non-blocking): %s", exc)

            result = await fn(*args, **kwargs)

            try:
                from app.db.redis import get_redis
                redis = get_redis()
                await redis.setex(key, ttl, json.dumps(result, default=str))
                logger.debug("Cache set: %s (ttl=%ds)", key, ttl)
            except Exception as exc:
                logger.debug("Cache write failed (non-blocking): %s", exc)

            return result

        wrapper.cache_key_fn = lambda *a, **kw: _make_cache_key(prefix, a, kw)
        return wrapper

    return decorator


async def invalidate_cache(key_prefix: str, *args, **kwargs) -> None:
    """Delete a specific cache entry."""
    key = _make_cache_key(key_prefix, args, kwargs)
    try:
        from app.db.redis import get_redis
        redis = get_redis()
        await redis.delete(key)
        logger.debug("Cache invalidated: %s", key)
    except Exception as exc:
        logger.debug("Cache invalidation failed: %s", exc)


# ── 3. Presigned URL cache ────────────────────────────────────────────────────

_URL_CACHE_TTL = 3000  # 50 min — presigned URLs expire in 60 min


async def get_cached_presigned_url(bucket: str, key: str) -> str | None:
    """Return a cached presigned URL if available and not near expiry."""
    try:
        from app.db.redis import get_redis
        redis = get_redis()
        cache_key = f"presigned:{bucket}:{key}"
        url = await redis.get(cache_key)
        return url.decode() if url else None
    except Exception:
        return None


async def cache_presigned_url(bucket: str, key: str, url: str) -> None:
    """Store a presigned URL in Redis for near the full presign duration."""
    try:
        from app.db.redis import get_redis
        redis = get_redis()
        cache_key = f"presigned:{bucket}:{key}"
        await redis.setex(cache_key, _URL_CACHE_TTL, url)
    except Exception:
        pass


# ── 4. DB query helpers ───────────────────────────────────────────────────────

def apply_pagination(query, page: int = 1, page_size: int = 20):
    """Apply LIMIT/OFFSET pagination to a SQLAlchemy select statement."""
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    return query.limit(page_size).offset((page - 1) * page_size)
