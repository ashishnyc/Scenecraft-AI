"""Task CRUD and lifecycle state machine endpoints."""
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.character import Character, CharacterCasting
from app.models.project import Project
from app.models.review_action import ReviewAction, ReviewActionType
from app.models.task import Task, TaskStatus
from app.schemas.task import TaskCreate, TaskResponse, TaskTransitionRequest, TaskUpdate
from app.services.state_machine import InvalidTransitionError, TransitionGuardError, validate_transition
from app.services.pubsub import publish_task_event

router = APIRouter(tags=["tasks"])


@router.post("/projects/{project_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    project_id: uuid.UUID,
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    task = Task(id=uuid.uuid4(), project_id=project_id, **body.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/projects/{project_id}/tasks", response_model=list[TaskResponse])
async def list_tasks(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    result = await db.execute(select(Task).where(Task.project_id == project_id).order_by(Task.title))
    return result.scalars().all()


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    return task


async def _run_outline_for_task(task_id: uuid.UUID) -> None:
    """Background job: stages 1-4 of the script pipeline.

    Stage 1 — generate 3-act outline
    Stage 2 — expand every scene into full screenplay format
    Stage 3 — consistency check (re-generates blocker scenes once if needed)
    Stage 4 — copyright scan (rewrites flagged scenes in-place)
    """
    from app.db.postgres import AsyncSessionLocal
    from app.models.project import ProjectType
    from app.models.workspace import Workspace
    from app.services.consistency_checker import check_consistency
    from app.services.copyright_scanner import scan_copyright
    from app.services.outline_generator import generate_outline
    from app.services.scene_expander import expand_scenes
    from app.services.story_bible import blank_bible

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return

        project = await db.get(Project, task.project_id)
        if project is None:
            return

        # Gather cast profiles (name → personality_prompt) from the project's castings
        result = await db.execute(
            select(Character.name, Character.personality_prompt)
            .join(CharacterCasting, CharacterCasting.character_id == Character.id)
            .where(CharacterCasting.project_id == project.id)
        )
        cast_profiles: dict[str, str | None] = {name: prompt for name, prompt in result.all()}
        cast_names = list(cast_profiles.keys())

        workspace = await db.get(Workspace, project.workspace_id)
        style_guide = (workspace.style_guide or {}) if workspace else {}

        # Inject story bible for serialised projects (SA-23)
        story_bible = None
        if project.type == ProjectType.serialised:
            story_bible = project.story_bible or blank_bible()

        # Stage 1 — outline
        outline = await generate_outline(
            task_id=str(task.id),
            concept_brief=task.concept_brief or "",
            creator_notes=task.creator_notes,
            style_guide=style_guide,
            cast_names=cast_names,
            story_bible=story_bible,
        )
        if outline is None:
            return

        current_script = dict(task.script or {})
        current_script["outline"] = outline
        task.script = current_script
        await db.commit()

        # Stage 2 — scene expansion
        full_script = await expand_scenes(
            task_id=str(task.id),
            outline=outline,
            cast_profiles=cast_profiles,
        )
        if full_script is None:
            return

        current_script = dict(task.script or {})
        current_script["full_script"] = full_script
        task.script = current_script
        await db.commit()

        # Stage 3 — consistency check
        consistency_report = await check_consistency(
            task_id=str(task.id),
            full_script=full_script,
            style_guide=style_guide,
            cast_profiles=cast_profiles,
            outline=outline,
        )
        if consistency_report is not None:
            current_script = dict(task.script or {})
            current_script["consistency_flags"] = consistency_report["flags"]
            task.script = current_script
            await db.commit()

        # Stage 4 — copyright scan
        scan_result = await scan_copyright(
            task_id=str(task.id),
            full_script=full_script,
            workspace_id=str(project.workspace_id),
        )
        if scan_result is not None:
            updated_full_script, copyright_report = scan_result
            current_script = dict(task.script or {})
            current_script["full_script"] = updated_full_script
            current_script["copyright_flags"] = copyright_report
            task.script = current_script
            await db.commit()


@router.post("/tasks/{task_id}/transition", response_model=TaskResponse)
async def transition_task(
    task_id: uuid.UUID,
    body: TaskTransitionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    try:
        validate_transition(task.status, body.status, task)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TransitionGuardError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    old_status = task.status
    task.status = body.status

    # Log transition to review_actions
    review = ReviewAction(
        id=uuid.uuid4(),
        task_id=task.id,
        action=ReviewActionType.approve,
        notes=f"Status transition: {old_status.value} → {body.status.value}",
    )
    db.add(review)

    await db.commit()
    await db.refresh(task)

    # Broadcast status change over WebSocket
    project = await db.get(Project, task.project_id)
    if project:
        await publish_task_event(
            task_id=str(task.id),
            status=task.status.value,
            workspace_id=str(project.workspace_id),
        )

    # Trigger outline generation when entering scripting state
    if body.status == TaskStatus.scripting:
        background_tasks.add_task(_run_outline_for_task, task.id)

    # Update story bible when script is approved (script_review → producing)
    if old_status == TaskStatus.script_review and body.status == TaskStatus.producing:
        background_tasks.add_task(_update_story_bible_for_task, task.id)

    return task


async def _update_story_bible_for_task(task_id: uuid.UUID) -> None:
    """Background job: extract episode events and update the project's story bible."""
    from app.db.postgres import AsyncSessionLocal
    from app.models.project import ProjectType
    from app.services.story_bible import extract_episode_events, merge_bible

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return

        project = await db.get(Project, task.project_id)
        if project is None or project.type != ProjectType.serialised:
            return

        full_script = (task.script or {}).get("full_script")
        if not full_script:
            return

        episode_number = len((project.story_bible or {}).get("previous_episodes", [])) + 1
        new_events = await extract_episode_events(
            task_id=str(task.id),
            full_script=full_script,
            existing_bible=project.story_bible,
            episode_number=episode_number,
        )
        if new_events is not None:
            project.story_bible = merge_bible(project.story_bible, new_events)
            await db.commit()
