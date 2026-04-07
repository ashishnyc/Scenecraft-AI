"""Workspace CRUD endpoints."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceCreate, WorkspaceResponse, WorkspaceUpdate
from app.services.youtube_service import get_youtube_connect_url, exchange_youtube_code, validate_youtube_channel

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("/validate-channel")
async def validate_channel(
    channel_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Validate a YouTube channel ID or handle against the YouTube Data API."""
    try:
        result = await validate_youtube_channel(channel_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="YouTube API error") from exc
    return result


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    # Validate the YouTube channel exists before saving
    try:
        result = await validate_youtube_channel(body.youtube_channel_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="YouTube API error") from exc

    if not result["valid"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="YouTube channel not found. Check the channel ID or handle and try again.",
        )

    # Store the canonical channel ID (resolved from handle if needed)
    data = body.model_dump()
    data["youtube_channel_id"] = result["channel_id"]

    workspace = Workspace(id=uuid.uuid4(), **data)
    db.add(workspace)
    await db.flush()  # get workspace.id before commit

    # Auto-create the "One-Offs" catch-all series for standalone videos
    from app.models.project import Project, ProjectType
    one_offs = Project(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        name="One-Offs",
        type=ProjectType.anthology,
        story_bible={"series_concept": "Standalone videos that don't belong to a specific series."},
    )
    db.add(one_offs)

    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(select(Workspace).order_by(Workspace.created_at.desc()))
    return result.scalars().all()


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(workspace, field, value)

    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    await db.delete(workspace)
    await db.commit()


# --- YouTube OAuth linking ---

@router.get("/{workspace_id}/youtube/connect")
async def youtube_connect(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    """Redirect the user to Google's YouTube OAuth consent page."""
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=get_youtube_connect_url(state=str(workspace_id)))


@router.get("/{workspace_id}/youtube/callback", response_model=WorkspaceResponse)
async def youtube_callback(
    workspace_id: uuid.UUID,
    code: str,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    """Google calls back here; exchange the code and store the YouTube token."""
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    try:
        channel_id, oauth_token = await exchange_youtube_code(code)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="YouTube OAuth exchange failed") from exc

    workspace.youtube_channel_id = channel_id
    workspace.youtube_oauth_token = oauth_token
    await db.commit()
    await db.refresh(workspace)
    return workspace
