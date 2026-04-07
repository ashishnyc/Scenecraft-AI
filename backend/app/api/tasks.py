"""Task CRUD and lifecycle state machine endpoints."""
import logging
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

logger = logging.getLogger(__name__)
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


# ── Generate brief with AI ────────────────────────────────────────────────────

from pydantic import BaseModel as _PydanticBase


class GenerateBriefResponse(_PydanticBase):
    concept_brief: str


@router.post("/tasks/{task_id}/generate-brief", response_model=GenerateBriefResponse)
async def generate_brief(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    """Use AI to generate a concept brief from the task title and series context."""
    from app.services.llm_client import llm_chat, resolve_ai_config

    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    project = await db.get(Project, task.project_id)
    series_concept = ""
    if project and project.story_bible:
        series_concept = (project.story_bible or {}).get("series_concept", "")

    workspace_id = str(project.workspace_id) if project else None
    cfg = await resolve_ai_config(workspace_id, "pitch_generation", db) if workspace_id else None

    series_ctx = f"\nSeries: {project.name}" if project else ""
    if series_concept:
        series_ctx += f"\nSeries concept: {series_concept}"

    brief_text = await llm_chat(
        system=(
            "You are a YouTube content strategist. Generate a compelling video concept brief "
            "in 2-3 sentences. Describe what the video will cover, the key story angle, and "
            "why viewers will find it compelling. Be specific and vivid. Return only the brief text."
        ),
        user=f"{series_ctx}\nVideo title: {task.title}".strip(),
        config=cfg,
    )

    return GenerateBriefResponse(concept_brief=brief_text.strip())


# ── Originality check ─────────────────────────────────────────────────────────

class OriginalityResponse(_PydanticBase):
    originality_score: float
    max_similarity: float
    low_originality: bool
    similar_videos: list[dict]


@router.post("/tasks/{task_id}/check-originality", response_model=OriginalityResponse)
async def check_originality(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user_id: str = Depends(get_current_user_id),
):
    """Check whether the task's concept brief is original vs existing workspace videos."""
    from app.services.originality_checker import check_pitch_originality

    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    project = await db.get(Project, task.project_id)
    workspace_id = str(project.workspace_id) if project else None
    if not workspace_id:
        raise HTTPException(status_code=400, detail="Task has no workspace")

    brief = task.concept_brief or task.title
    result = await check_pitch_originality(brief, workspace_id)
    return result


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
            db=db,
            workspace_id=project.workspace_id,
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
            db=db,
            workspace_id=project.workspace_id,
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
            db=db,
            workspace_id=project.workspace_id,
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
            db=db,
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

    # Trigger audio pipeline when entering audio_preview state
    if body.status == TaskStatus.audio_preview:
        changed_scenes: set[int] | None = (
            set(body.changed_scene_numbers) if getattr(body, "changed_scene_numbers", None) else None
        )
        background_tasks.add_task(_run_audio_pipeline, task.id, changed_scenes)

    # Mark audio stems as approved when script is approved (audio_preview → script_review)
    if old_status == TaskStatus.audio_preview and body.status == TaskStatus.script_review:
        background_tasks.add_task(_approve_audio_stems, task.id)

    # Update story bible when script is approved (script_review → producing)
    if old_status == TaskStatus.script_review and body.status == TaskStatus.producing:
        background_tasks.add_task(_update_story_bible_for_task, task.id)

    # Trigger video production pipeline when entering producing state
    if body.status == TaskStatus.producing:
        # Check if this is a re-edit (flagged shots exist from Gate 2 review)
        script = task.script or {}
        flagged = (script.get("video_review") or {}).get("flagged_shot_indices", [])
        if flagged and old_status == TaskStatus.final_review:
            background_tasks.add_task(_run_scene_re_edit, task.id)
        else:
            background_tasks.add_task(_run_video_pipeline, task.id)

    # Trigger YouTube upload when task moves to scheduled
    if body.status == TaskStatus.scheduled:
        background_tasks.add_task(_run_youtube_upload, task.id)

    return task


async def _run_audio_pipeline(task_id: uuid.UUID, changed_scenes: set[int] | None) -> None:
    """Background job: voice routing → synthesis → assembly.

    When *changed_scenes* is provided (selective re-generation, SA-28), only
    those scenes are re-synthesised; existing stems for other scenes are reused.
    """
    from decimal import Decimal
    from app.db.postgres import AsyncSessionLocal
    from app.models.workspace import Workspace
    from app.services.audio_assembler import assemble_audio
    from app.services.voice_router import build_routing_manifest
    from app.services.voice_synthesizer import synthesize_manifest

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return

        script = task.script or {}
        full_script = script.get("full_script")
        if not full_script:
            logger.warning("No full_script for audio pipeline (task %s)", task_id)
            return

        project = await db.get(Project, task.project_id)
        if project is None:
            return

        workspace = await db.get(Workspace, project.workspace_id)
        style_guide = (workspace.style_guide or {}) if workspace else {}
        narrator_voice_id = style_guide.get("narrator_voice_id", "narrator")

        # Gather cast voice profiles
        result = await db.execute(
            select(Character.name, Character.voice_profile_id)
            .join(CharacterCasting, CharacterCasting.character_id == Character.id)
            .where(CharacterCasting.project_id == project.id)
        )
        cast_voice_profiles: dict[str, str | None] = {name: vid for name, vid in result.all()}

        # SA-24: build routing manifest
        routing_manifest = build_routing_manifest(full_script, cast_voice_profiles, narrator_voice_id)
        if not routing_manifest:
            logger.warning("Empty routing manifest for task %s", task_id)
            return

        # SA-25: synthesise (full or selective)
        existing_stems: dict[int, str] = {}
        if changed_scenes is not None:
            # Reuse stems from previous run for unchanged scenes
            existing_stems = {
                s["line_index"]: s["s3_url"]
                for s in script.get("audio_stems", {}).get("stems", [])
                if s["scene_number"] not in changed_scenes
            }

        new_stems, cost = await synthesize_manifest(
            task_id=str(task_id),
            routing_manifest=routing_manifest,
            scene_numbers=changed_scenes,
        )
        all_stems = {**existing_stems, **new_stems}

        # SA-26 + SA-29: assemble and build stem registry
        result_data = await assemble_audio(str(task_id), routing_manifest, all_stems)
        if result_data is None:
            return

        _, stem_registry = result_data

        current_script = dict(task.script or {})
        current_script["audio_stems"] = stem_registry
        task.script = current_script

        # Accumulate cost on task
        existing_cost = Decimal(str(task.total_cost_usd or 0))
        task.total_cost_usd = existing_cost + cost

        await db.commit()


async def _approve_audio_stems(task_id: uuid.UUID) -> None:
    """Mark all audio stems as approved when task moves to script_review."""
    from app.db.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return
        script = dict(task.script or {})
        stems_data = script.get("audio_stems")
        if stems_data:
            stems_data["approved"] = True
            for stem in stems_data.get("stems", []):
                stem["approved"] = True
            script["audio_stems"] = stems_data
            task.script = script
            await db.commit()


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
            db=db,
            workspace_id=project.workspace_id,
        )
        if new_events is not None:
            project.story_bible = merge_bible(project.story_bible, new_events)
            await db.commit()


async def _run_video_pipeline(task_id: uuid.UUID) -> None:
    """Background job: SA-30 through SA-36 video production pipeline.

    SA-30 — plan shots → shot_list
    SA-31 — build character reference prompts
    SA-32 — generate environment plates
    SA-33 — generate video clips (batched)
    SA-34 — generate music tracks
    SA-35 — assemble final video
    SA-36 — quality check; auto-advances to final_review on pass
    """
    from decimal import Decimal
    from app.db.postgres import AsyncSessionLocal
    from app.models.workspace import Workspace
    from app.services.character_consistency import build_cast_reference_prompts
    from app.services.environment_generator import generate_environment_plates
    from app.services.music_generator import generate_music
    from app.services.scene_planner import plan_shots
    from app.services.video_assembler import assemble_video
    from app.services.video_clip_generator import generate_clips
    from app.services.video_quality_checker import check_quality

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return

        script = task.script or {}
        full_script = script.get("full_script")
        if not full_script:
            logger.warning("No full_script for video pipeline (task %s)", task_id)
            return

        audio_stems = script.get("audio_stems")
        project = await db.get(Project, task.project_id)
        if project is None:
            return

        # Gather cast for character consistency (SA-31)
        result = await db.execute(
            select(
                Character.name,
                Character.personality_prompt,
                Character.visual_references,
                CharacterCasting.appearance_override,
            )
            .join(CharacterCasting, CharacterCasting.character_id == Character.id)
            .where(CharacterCasting.project_id == project.id)
        )
        cast = [
            {"name": name, "personality_prompt": pp, "visual_references": vr, "appearance_override": ao}
            for name, pp, vr, ao in result.all()
        ]
        reference_prompts = build_cast_reference_prompts(cast)

        # SA-30: plan shots
        shot_list = await plan_shots(str(task_id), full_script, audio_stems, db=db, workspace_id=project.workspace_id)
        if shot_list is None:
            return

        current = dict(task.script or {})
        current["shot_list"] = shot_list
        task.script = current
        await db.commit()

        # SA-32: environment plates
        env_plates = await generate_environment_plates(
            str(task_id), str(project.id), shot_list
        )

        # SA-33: video clips
        settings_obj = __import__("app.core.config", fromlist=["get_settings"]).get_settings()
        batch_size = getattr(settings_obj, "VIDEO_CLIP_BATCH_SIZE", 5)
        clip_urls, clip_cost = await generate_clips(
            str(task_id), shot_list, reference_prompts, env_plates, batch_size
        )

        current = dict(task.script or {})
        current["video_clips"] = {str(k): v for k, v in clip_urls.items()}
        task.script = current
        task.total_cost_usd = (Decimal(str(task.total_cost_usd or 0)) + clip_cost)
        await db.commit()

        # SA-34: music
        music_urls, music_cost = await generate_music(str(task_id), shot_list, audio_stems)

        current = dict(task.script or {})
        current["music_tracks"] = {str(k): v for k, v in music_urls.items()}
        task.script = current
        task.total_cost_usd = (Decimal(str(task.total_cost_usd or 0)) + music_cost)
        await db.commit()

        # SA-35: assemble video
        final_url = await assemble_video(
            task_id=str(task_id),
            shot_list=shot_list,
            clip_s3_urls=clip_urls,
            audio_stems=audio_stems,
            music_s3_urls=music_urls,
            title=task.title,
        )
        if final_url is None:
            return

        task.final_video_url = final_url
        await db.commit()

        # SA-36: quality check
        quality_report = await check_quality(str(task_id), final_url, shot_list, audio_stems)
        if quality_report is not None:
            current = dict(task.script or {})
            current["quality_report"] = quality_report
            task.script = current
            await db.commit()

            if quality_report.get("passed"):
                # Auto-advance to final_review
                from app.services.state_machine import validate_transition
                try:
                    validate_transition(task.status, TaskStatus.final_review, task)
                    task.status = TaskStatus.final_review
                    await db.commit()
                    workspace = await db.get(Workspace, project.workspace_id)
                    if workspace:
                        from app.services.pubsub import publish_task_event
                        await publish_task_event(
                            task_id=str(task_id),
                            status=TaskStatus.final_review.value,
                            workspace_id=str(workspace.id),
                        )
                except Exception as exc:
                    logger.warning("Could not auto-advance to final_review (task %s): %s", task_id, exc)


async def _run_scene_re_edit(task_id: uuid.UUID) -> None:
    """SA-41: Re-generate only flagged shots and re-assemble the video."""
    from app.services.scene_re_editor import re_edit_flagged_scenes
    logger.info("Starting scene re-edit for task %s", task_id)
    try:
        quality_report = await re_edit_flagged_scenes(str(task_id))
        if quality_report and quality_report.get("passed"):
            # Auto-advance back to final_review
            from app.db.postgres import AsyncSessionLocal
            from app.models.project import Project
            async with AsyncSessionLocal() as db:
                task = await db.get(Task, task_id)
                if task:
                    task.status = TaskStatus.final_review
                    await db.commit()
                    project = await db.get(Project, task.project_id)
                    if project:
                        from app.services.pubsub import publish_task_event
                        workspace = await db.get(Workspace, project.workspace_id)
                        if workspace:
                            await publish_task_event(
                                task_id=str(task_id),
                                status=TaskStatus.final_review.value,
                                workspace_id=str(workspace.id),
                            )
    except Exception as exc:
        logger.error("Scene re-edit failed for task %s: %s", task_id, exc)


async def _run_youtube_upload(task_id: uuid.UUID) -> None:
    """SA-43/SA-44: Schedule then upload final video + metadata + thumbnail to YouTube."""
    from app.services.youtube_uploader import upload_to_youtube
    from app.services.upload_scheduler import schedule_upload
    logger.info("Starting YouTube upload for task %s", task_id)
    try:
        schedule_info = await schedule_upload(str(task_id))
        logger.info("Upload schedule for task %s: %s", task_id, schedule_info)
    except Exception as exc:
        logger.warning("Upload scheduling failed for task %s: %s", task_id, exc)
    try:
        video_id = await upload_to_youtube(str(task_id))
        if video_id:
            from app.db.postgres import AsyncSessionLocal
            from app.models.project import Project
            async with AsyncSessionLocal() as db:
                task = await db.get(Task, task_id)
                if task:
                    task.youtube_video_id = video_id
                    task.status = TaskStatus.published
                    await db.commit()
                    project = await db.get(Project, task.project_id)
                    if project:
                        from app.services.pubsub import publish_task_event
                        workspace = await db.get(Workspace, project.workspace_id)
                        if workspace:
                            await publish_task_event(
                                task_id=str(task_id),
                                status=TaskStatus.published.value,
                                workspace_id=str(workspace.id),
                            )
            logger.info("Task %s published to YouTube: %s", task_id, video_id)
        else:
            logger.warning("YouTube upload returned no video_id for task %s", task_id)
    except Exception as exc:
        logger.error("YouTube upload failed for task %s: %s", task_id, exc)
