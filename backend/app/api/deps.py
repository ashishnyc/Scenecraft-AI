"""FastAPI dependencies shared across routers."""
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.services.jwt_service import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user_id(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Return the current user_id from JWT, or auto-login in dev mode."""
    settings = get_settings()

    if settings.DEV_AUTO_LOGIN:
        assert settings.DEBUG, "DEV_AUTO_LOGIN requires DEBUG=true — never enable in production"
        assert settings.DEV_AUTO_LOGIN_USER_EMAIL, "DEV_AUTO_LOGIN_USER_EMAIL must be set when DEV_AUTO_LOGIN=true"

        # Lazily import to avoid circular deps
        from sqlalchemy import select
        from app.db.postgres import AsyncSessionLocal
        from app.models.user import User

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.email == settings.DEV_AUTO_LOGIN_USER_EMAIL))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    id=uuid.uuid4(),
                    email=settings.DEV_AUTO_LOGIN_USER_EMAIL,
                    name="Dev User",
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
        return str(user.id)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
