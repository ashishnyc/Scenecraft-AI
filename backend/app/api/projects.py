"""Project CRUD endpoints."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.project import Project
from app.models.workspace import Workspace
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(tags=["projects"])


class ProjectSuggestRequest(BaseModel):
    brief: str


class VideoConceptSuggestion(BaseModel):
    title: str
    concept: str


class ProjectSuggestResponse(BaseModel):
    name: str
    series_concept: str
    video_concepts: list[VideoConceptSuggestion]


@router.post("/workspaces/{workspace_id}/projects/suggest", response_model=ProjectSuggestResponse)
async def suggest_project(
    workspace_id: uuid.UUID,
    body: ProjectSuggestRequest,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    """Use the LLM to suggest a project name and base video concepts from a free-text brief."""
    from app.services.project_suggester import suggest_project as _suggest
    from app.services.llm_client import resolve_ai_config
    config = await resolve_ai_config(workspace_id, "project_suggestions", db)
    result = _suggest(body.brief, config=config)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM unavailable — check AI configuration in workspace settings.",
        )
    return result


@router.post("/workspaces/{workspace_id}/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    workspace_id: uuid.UUID,
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    project = Project(id=uuid.uuid4(), workspace_id=workspace_id, **body.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/workspaces/{workspace_id}/projects", response_model=list[ProjectResponse])
async def list_projects(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    workspace = await db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    result = await db.execute(
        select(Project).where(Project.workspace_id == workspace_id).order_by(Project.name)
    )
    projects = result.scalars().all()

    # Ensure every workspace always has a "One-Offs" catch-all series
    if not any(p.name == "One-Offs" for p in projects):
        from app.models.project import ProjectType
        one_offs = Project(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            name="One-Offs",
            type=ProjectType.anthology,
            story_bible={"series_concept": "Standalone videos that don't belong to a specific series."},
        )
        db.add(one_offs)
        await db.commit()
        projects = list(projects) + [one_offs]

    return projects


class ConceptGenerateRequest(BaseModel):
    brief: str | None = None  # optional extra context; if omitted uses project name


@router.post("/projects/{project_id}/concepts/generate", response_model=list[VideoConceptSuggestion])
async def generate_concepts(
    project_id: uuid.UUID,
    body: ConceptGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    """Generate additional episode concept ideas for an existing project."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    from app.services.project_suggester import generate_concepts as _gen
    from app.services.llm_client import resolve_ai_config
    config = await resolve_ai_config(project.workspace_id, "project_suggestions", db)
    brief = body.brief or project.name
    story_bible = project.story_bible or {}
    result = _gen(
        brief=brief,
        series_concept=story_bible.get("series_concept", ""),
        existing_concepts=story_bible.get("base_video_concepts", []),
        config=config,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM unavailable — check AI configuration in workspace settings.",
        )
    return result


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await db.delete(project)
    await db.commit()
