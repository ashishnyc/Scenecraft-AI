"""Security hardening (SA-54).

Provides:
  1. Rate limiting middleware (per-IP sliding window via Redis)
  2. Input sanitisation helpers (strip control characters, limit lengths)
  3. RBAC dependency (workspace ownership check)
  4. Secrets validation at startup (warn if weak SECRET_KEY)
  5. Security headers middleware

Intentionally does NOT wrap existing auth (jwt_service.py is solid) —
instead adds defence-in-depth layers.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
import unicodedata
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── 1. Rate limiting ──────────────────────────────────────────────────────────

_RATE_LIMIT_WINDOW = 60          # seconds
_RATE_LIMIT_MAX_REQUESTS = 120   # per window per IP
_RATE_LIMIT_STRICT = 20          # tighter limit for auth endpoints


async def _get_redis_ratelimit():
    from app.db.redis import get_redis
    return get_redis()


async def check_rate_limit(request: Request, max_requests: int = _RATE_LIMIT_MAX_REQUESTS) -> None:
    """
    Sliding window rate limiter using Redis.
    Raises HTTP 429 if the client exceeds *max_requests* in the window.
    """
    try:
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{client_ip}:{int(time.time()) // _RATE_LIMIT_WINDOW}"

        redis = await _get_redis_ratelimit()
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, _RATE_LIMIT_WINDOW * 2)
        results = await pipe.execute()
        count = results[0]

        if count > max_requests:
            logger.warning("Rate limit exceeded for IP %s (%d/%d)", client_ip, count, max_requests)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests — please slow down.",
                headers={"Retry-After": str(_RATE_LIMIT_WINDOW)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        # Never block requests due to Redis failure
        logger.warning("Rate limit check failed (non-blocking): %s", exc)


async def strict_rate_limit(request: Request) -> None:
    """Stricter rate limit for auth endpoints (20 req/min)."""
    await check_rate_limit(request, max_requests=_RATE_LIMIT_STRICT)


# ── 2. Input sanitisation ─────────────────────────────────────────────────────

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitise_string(value: str, max_length: int = 10_000) -> str:
    """
    Strip null bytes and control characters; enforce max length.
    Normalise to NFC Unicode.
    """
    if not isinstance(value, str):
        return str(value)[:max_length]
    value = unicodedata.normalize("NFC", value)
    value = _CONTROL_CHAR_RE.sub("", value)
    return value[:max_length]


def sanitise_dict(data: dict[str, Any], max_depth: int = 5) -> dict[str, Any]:
    """Recursively sanitise string values in a dict."""
    if max_depth <= 0:
        return {}
    result = {}
    for k, v in data.items():
        key = sanitise_string(str(k), max_length=256)
        if isinstance(v, str):
            result[key] = sanitise_string(v)
        elif isinstance(v, dict):
            result[key] = sanitise_dict(v, max_depth - 1)
        elif isinstance(v, list):
            result[key] = [
                sanitise_string(i) if isinstance(i, str) else i
                for i in v[:500]
            ]
        else:
            result[key] = v
    return result


# ── 3. RBAC — workspace ownership check ──────────────────────────────────────

async def require_workspace_access(
    workspace_id: str,
    user_id: str,
    db,
) -> None:
    """
    Raise HTTP 403 if *user_id* does not have access to *workspace_id*.

    Currently checks workspace.owner_id == user_id.
    Extend this to a proper membership table when multi-user workspaces are added.
    """
    from app.models.workspace import Workspace
    from sqlalchemy import select

    workspace = (await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )).scalar_one_or_none()

    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    if str(workspace.owner_id) != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace",
        )


# ── 4. Startup secrets validation ─────────────────────────────────────────────

_MIN_SECRET_KEY_ENTROPY_BITS = 128  # 16 bytes


def validate_secrets_at_startup() -> list[str]:
    """
    Check for weak or placeholder secrets. Returns list of warning strings.
    Called from app lifespan.
    """
    settings = get_settings()
    warnings = []

    # SECRET_KEY strength
    key = settings.SECRET_KEY
    entropy_bits = len(set(key)) * len(key).bit_length()
    if len(key) < 32:
        warnings.append(f"SECRET_KEY is too short ({len(key)} chars) — use at least 32 random chars")
    if key in ("secret", "changeme", "your-secret-key", ""):
        warnings.append("SECRET_KEY appears to be a placeholder — rotate immediately")

    # DEV_AUTO_LOGIN in non-debug mode
    if settings.DEV_AUTO_LOGIN and not settings.DEBUG:
        warnings.append("DEV_AUTO_LOGIN is enabled without DEBUG=true — this should never happen in production")

    # Warn about missing Ollama config
    if not settings.OLLAMA_BASE_URL:
        warnings.append("OLLAMA_BASE_URL is not set — LLM features will be disabled")

    for w in warnings:
        logger.warning("SECURITY: %s", w)

    return warnings


# ── 5. Security headers middleware ────────────────────────────────────────────

async def add_security_headers(request: Request, call_next):
    """FastAPI middleware to add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
