"""Unit tests for JWT service (SA-3).

Tests cover token creation, validation, expiry, and tamper detection.
No live database or Google credentials required.
"""
import time
import pytest
from unittest.mock import patch
from datetime import timedelta

# Provide minimal required env vars so get_settings() succeeds
import os
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("S3_BUCKET", "test")
os.environ.setdefault("SECRET_KEY", "supersecrettestkey1234567890abcdef")


from app.services.jwt_service import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)


USER_ID = "550e8400-e29b-41d4-a716-446655440000"


def test_access_token_roundtrip():
    token = create_access_token(USER_ID)
    assert decode_access_token(token) == USER_ID


def test_refresh_token_roundtrip():
    token = create_refresh_token(USER_ID)
    assert decode_refresh_token(token) == USER_ID


def test_access_token_rejected_as_refresh():
    token = create_access_token(USER_ID)
    with pytest.raises(ValueError, match="Wrong token type"):
        decode_refresh_token(token)


def test_refresh_token_rejected_as_access():
    token = create_refresh_token(USER_ID)
    with pytest.raises(ValueError, match="Wrong token type"):
        decode_access_token(token)


def test_tampered_token_rejected():
    token = create_access_token(USER_ID)
    tampered = token[:-4] + "xxxx"
    with pytest.raises(ValueError):
        decode_access_token(tampered)


def test_expired_access_token_rejected():
    from app.services import jwt_service
    with patch.object(jwt_service, "_create_token", wraps=jwt_service._create_token) as _:
        # Create token that expired 1 second ago
        from datetime import datetime, timezone
        from jose import jwt as jose_jwt
        from app.core.config import get_settings
        settings = get_settings()
        payload = {
            "sub": USER_ID,
            "type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        expired_token = jose_jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    with pytest.raises(ValueError, match="Invalid or expired token"):
        decode_access_token(expired_token)


def test_wrong_secret_rejected():
    from jose import jwt as jose_jwt
    from datetime import datetime, timezone
    payload = {
        "sub": USER_ID,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    bad_token = jose_jwt.encode(payload, "wrongsecret", algorithm="HS256")
    with pytest.raises(ValueError):
        decode_access_token(bad_token)
