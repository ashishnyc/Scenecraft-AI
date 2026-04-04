"""JWT token creation and validation."""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

_ACCESS_TOKEN_TYPE = "access"
_REFRESH_TOKEN_TYPE = "refresh"


def _create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _create_token(
        subject=user_id,
        token_type=_ACCESS_TOKEN_TYPE,
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        subject=user_id,
        token_type=_REFRESH_TOKEN_TYPE,
        expires_delta=timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_access_token(token: str) -> str:
    """Return user_id (sub) from a valid access token, raise ValueError otherwise."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc

    if payload.get("type") != _ACCESS_TOKEN_TYPE:
        raise ValueError("Wrong token type")

    sub = payload.get("sub")
    if not sub:
        raise ValueError("Token missing subject")
    return sub


def decode_refresh_token(token: str) -> str:
    """Return user_id (sub) from a valid refresh token, raise ValueError otherwise."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc

    if payload.get("type") != _REFRESH_TOKEN_TYPE:
        raise ValueError("Wrong token type")

    sub = payload.get("sub")
    if not sub:
        raise ValueError("Token missing subject")
    return sub
