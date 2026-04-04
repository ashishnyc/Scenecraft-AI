"""Auth router — Google OAuth2 login flow + JWT token refresh."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.user import User
from app.services.jwt_service import create_access_token, create_refresh_token, decode_refresh_token
from app.services.oauth_service import exchange_code_for_user_info, get_google_auth_url

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


@router.get("/login")
async def login():
    """Redirect the browser to Google's OAuth2 consent page."""
    return RedirectResponse(url=get_google_auth_url())


@router.get("/callback", response_model=TokenResponse)
async def callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Google redirects here with an auth code; exchange it and return JWT tokens."""
    try:
        userinfo = await exchange_code_for_user_info(code)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth exchange failed") from exc

    email: str = userinfo.get("email", "")
    name: str = userinfo.get("name", "")
    google_oauth_token: str | None = userinfo.get("google_oauth_token")

    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No email returned from Google")

    # Upsert user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(id=uuid.uuid4(), email=email, name=name, google_oauth_token=google_oauth_token)
        db.add(user)
    else:
        user.name = name
        if google_oauth_token:
            user.google_oauth_token = google_oauth_token

    await db.commit()
    await db.refresh(user)

    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    try:
        user_id = decode_refresh_token(body.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.get("/me")
async def me(user_id: str = Depends(get_current_user_id)):
    """Return the current user's ID — a simple protected route to verify auth works."""
    return {"user_id": user_id}
