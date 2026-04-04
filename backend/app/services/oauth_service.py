"""Google OAuth2 helpers — builds redirect URL and exchanges the auth code for user info."""
import httpx

from app.core.config import get_settings

settings = get_settings()

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_SCOPES = "openid email profile"


def get_google_auth_url(state: str = "") -> str:
    """Return the Google OAuth2 authorization URL to redirect the user to."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": _SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{_GOOGLE_AUTH_URL}?{query}"


async def exchange_code_for_user_info(code: str) -> dict:
    """Exchange authorization code for tokens and return Google user info."""
    async with httpx.AsyncClient() as client:
        # Step 1: exchange code for tokens
        token_resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        # Step 2: fetch user info
        userinfo_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()
        userinfo["google_oauth_token"] = tokens.get("refresh_token") or tokens.get("access_token")
        return userinfo
