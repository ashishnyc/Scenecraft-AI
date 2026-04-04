"""YouTube OAuth2 helpers — build consent URL and exchange auth code for channel + token."""
import httpx

from app.core.config import get_settings

settings = get_settings()

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

_YOUTUBE_REDIRECT_URI = "http://localhost:8000/workspaces/{workspace_id}/youtube/callback"
_SCOPES = "https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/youtube.upload"


def get_youtube_connect_url(state: str = "") -> str:
    """Return the YouTube OAuth2 authorization URL; state carries the workspace_id."""
    redirect_uri = f"http://localhost:8000/workspaces/{state}/youtube/callback"
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{_GOOGLE_AUTH_URL}?{query}"


async def exchange_youtube_code(code: str, workspace_id: str = "") -> tuple[str, str]:
    """Exchange auth code for tokens; return (youtube_channel_id, oauth_token)."""
    redirect_uri = f"http://localhost:8000/workspaces/{workspace_id}/youtube/callback"
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()
        access_token = tokens["access_token"]
        oauth_token = tokens.get("refresh_token") or access_token

        # Fetch the authenticated user's YouTube channel
        channels_resp = await client.get(
            _YOUTUBE_CHANNELS_URL,
            params={"part": "id", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        channels_resp.raise_for_status()
        items = channels_resp.json().get("items", [])
        if not items:
            raise ValueError("No YouTube channel found for this Google account")
        channel_id = items[0]["id"]

    return channel_id, oauth_token
