"""Instagram management API (SA-65–67)."""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user_id
from app.db.postgres import get_db
from app.models.instagram import InstagramPost, InstagramComment, PostStatus, CommentReplyStatus

router = APIRouter(tags=["instagram"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class PostCreate(BaseModel):
    workspace_id: uuid.UUID
    character_id: uuid.UUID | None = None
    post_type: str = Field(default="image", pattern="^(image|carousel|reel|story)$")
    prompt_context: str = Field(..., min_length=1)
    media_urls: list[str] = Field(default_factory=list)


class PostSchedule(BaseModel):
    scheduled_at: datetime


class PostResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    character_id: uuid.UUID | None
    post_type: str
    status: str
    caption: str | None
    hashtags: list[str]
    media_urls: list[str]
    instagram_post_id: str | None
    scheduled_at: datetime | None
    posted_at: datetime | None
    engagement_stats: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CommentResponse(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    instagram_comment_id: str
    author_username: str
    text: str
    reply_status: str
    generated_reply: str | None
    posted_reply: str | None
    safety_flags: dict | None

    model_config = {"from_attributes": True}


class ReplyApproval(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    edited_reply: str | None = None


# ── SA-65: Post generation & scheduling ──────────────────────────────────────

@router.post("/instagram/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_instagram_post(
    body: PostCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Generate + save a draft Instagram post via Claude."""
    from app.services.instagram_pipeline import create_draft_post
    post = await create_draft_post(
        workspace_id=str(body.workspace_id),
        character_id=str(body.character_id) if body.character_id else None,
        post_type=body.post_type,
        prompt_context=body.prompt_context,
        media_urls=body.media_urls,
    )
    return post


@router.get("/instagram/posts", response_model=list[PostResponse])
async def list_instagram_posts(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """List all posts for a workspace, newest first."""
    result = await db.execute(
        select(InstagramPost)
        .where(InstagramPost.workspace_id == workspace_id)
        .order_by(InstagramPost.created_at.desc())
    )
    return result.scalars().all()


@router.get("/instagram/posts/{post_id}", response_model=PostResponse)
async def get_instagram_post(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    post = await db.get(InstagramPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.post("/instagram/posts/{post_id}/schedule", response_model=PostResponse)
async def schedule_instagram_post(
    post_id: uuid.UUID,
    body: PostSchedule,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Schedule a draft post for publishing."""
    from app.services.instagram_pipeline import schedule_post
    try:
        post = await schedule_post(str(post_id), body.scheduled_at)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return post


@router.post("/instagram/posts/{post_id}/publish", response_model=PostResponse)
async def publish_instagram_post(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Immediately publish a post via Meta Graph API."""
    from app.services.instagram_pipeline import publish_post
    try:
        post = await publish_post(str(post_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return post


@router.delete("/instagram/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instagram_post(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    post = await db.get(InstagramPost, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    await db.delete(post)
    await db.commit()


# ── SA-66: Comment reply system ───────────────────────────────────────────────

@router.post("/instagram/posts/{post_id}/fetch-comments", response_model=list[CommentResponse])
async def fetch_comments(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Poll Meta API for new comments and store them."""
    from app.services.instagram_replies import fetch_post_comments
    await fetch_post_comments(str(post_id))
    result = await db.execute(
        select(InstagramComment)
        .where(InstagramComment.post_id == post_id)
        .order_by(InstagramComment.fetched_at.desc())
    )
    return result.scalars().all()


@router.get("/instagram/posts/{post_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """List all stored comments for a post."""
    result = await db.execute(
        select(InstagramComment)
        .where(InstagramComment.post_id == post_id)
        .order_by(InstagramComment.fetched_at.desc())
    )
    return result.scalars().all()


@router.post("/instagram/comments/{comment_id}/generate-reply", response_model=CommentResponse)
async def generate_comment_reply(
    comment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Generate an in-character LLM reply for a comment."""
    from app.services.instagram_replies import generate_reply
    await generate_reply(str(comment_id))
    comment = await db.get(InstagramComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    await db.refresh(comment)
    return comment


@router.put("/instagram/comments/{comment_id}/review", response_model=CommentResponse)
async def review_comment_reply(
    comment_id: uuid.UUID,
    body: ReplyApproval,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Approve or reject a generated reply. Optionally edit before approving."""
    comment = await db.get(InstagramComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if body.action == "approve":
        if body.edited_reply:
            comment.generated_reply = body.edited_reply
        comment.reply_status = CommentReplyStatus.approved
        # Auto-post approved replies
        from app.services.instagram_replies import post_reply
        await post_reply(str(comment_id))
    else:
        comment.reply_status = CommentReplyStatus.rejected

    await db.commit()
    await db.refresh(comment)
    return comment


# ── SA-67: Engagement dashboard ───────────────────────────────────────────────

@router.get("/instagram/workspaces/{workspace_id}/dashboard")
async def get_instagram_dashboard(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return aggregated Instagram stats for the management dashboard."""
    posts = (await db.execute(
        select(InstagramPost).where(InstagramPost.workspace_id == workspace_id)
    )).scalars().all()

    total_posts = len(posts)
    by_status = {}
    total_likes = 0
    total_comments_count = 0
    scheduled_posts = []

    for p in posts:
        s = p.status.value
        by_status[s] = by_status.get(s, 0) + 1
        stats = p.engagement_stats or {}
        total_likes += stats.get("like_count", 0)
        total_comments_count += stats.get("comments_count", 0)
        if p.status == PostStatus.scheduled and p.scheduled_at:
            scheduled_posts.append({
                "id": str(p.id),
                "caption_preview": (p.caption or "")[:60],
                "scheduled_at": p.scheduled_at.isoformat(),
                "post_type": p.post_type.value,
            })

    # Pending replies count
    pending_replies = (await db.execute(
        select(InstagramComment)
        .join(InstagramPost, InstagramComment.post_id == InstagramPost.id)
        .where(
            InstagramPost.workspace_id == workspace_id,
            InstagramComment.reply_status == CommentReplyStatus.pending,
            InstagramComment.generated_reply.isnot(None),
        )
    )).scalars().all()

    return {
        "total_posts": total_posts,
        "by_status": by_status,
        "total_likes": total_likes,
        "total_comments": total_comments_count,
        "pending_reply_reviews": len(pending_replies),
        "scheduled_posts": sorted(scheduled_posts, key=lambda x: x["scheduled_at"]),
    }
