"""Instagram content pipeline (SA-65).

Generates Instagram posts (caption + hashtags) from a character brief using
Claude, schedules them, and posts via the Meta Graph API.

Flow:
  1. generate_post_content(character_id, prompt_context) → caption + hashtags
  2. schedule_post(post_id, scheduled_at) → updates post status to 'scheduled'
  3. publish_post(post_id) → calls Meta Graph API, updates status to 'posted'
  4. Daily APScheduler job: publish_due_posts()
"""
from __future__ import annotations

import logging
import re
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.instagram import InstagramPost, PostStatus, PostType

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_CAPTION_CHARS = 2200
_MAX_HASHTAGS = 30


async def generate_post_content(
    workspace_id: str,
    character_id: str | None,
    prompt_context: str,
    post_type: str = "image",
) -> dict[str, Any]:
    """
    Use Claude to generate an in-character Instagram caption + hashtag set.

    Returns:
        {"caption": str, "hashtags": list[str], "alt_text": str}
    """
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — returning placeholder post content")
        return {
            "caption": prompt_context,
            "hashtags": ["#content", "#scenecraft"],
            "alt_text": "Image post",
        }

    character_context = ""
    if character_id:
        async for db in get_db():
            from app.models.character import Character
            from sqlalchemy import select
            char = (await db.execute(
                select(Character).where(Character.id == uuid.UUID(character_id))
            )).scalar_one_or_none()
            if char:
                character_context = f"""
CHARACTER: {char.name} ({char.role_type.value})
Personality: {char.personality_prompt or 'Not defined'}
Backstory: {char.backstory or 'Not defined'}
"""
            break

    prompt = f"""You are a social media content creator writing an Instagram post.
{character_context}
CONTEXT / BRIEF:
{prompt_context}

POST TYPE: {post_type}

Generate an engaging Instagram post. Return a JSON object with:
- "caption": the post caption (max {_MAX_CAPTION_CHARS} characters, no hashtags in caption)
- "hashtags": list of up to {_MAX_HASHTAGS} relevant hashtags (include the # symbol)
- "alt_text": a brief accessibility alt text for the image (1-2 sentences)

Return only the JSON object."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)

        # Validate + cap
        result["caption"] = str(result.get("caption", ""))[:_MAX_CAPTION_CHARS]
        result["hashtags"] = [str(h) for h in result.get("hashtags", [])][:_MAX_HASHTAGS]
        result["alt_text"] = str(result.get("alt_text", ""))
        return result
    except Exception as exc:
        logger.error("Post generation failed: %s", exc)
        return {"caption": prompt_context, "hashtags": [], "alt_text": ""}


async def create_draft_post(
    workspace_id: str,
    character_id: str | None,
    post_type: str,
    prompt_context: str,
    media_urls: list[str],
) -> InstagramPost:
    """Generate content and save as a draft InstagramPost."""
    content = await generate_post_content(workspace_id, character_id, prompt_context, post_type)

    async for db in get_db():
        post = InstagramPost(
            id=uuid.uuid4(),
            workspace_id=uuid.UUID(workspace_id),
            character_id=uuid.UUID(character_id) if character_id else None,
            post_type=PostType(post_type),
            status=PostStatus.draft,
            caption=content["caption"],
            hashtags=content["hashtags"],
            media_urls=media_urls,
            generation_metadata={
                "alt_text": content.get("alt_text", ""),
                "prompt_context": prompt_context[:500],
            },
        )
        db.add(post)
        await db.commit()
        await db.refresh(post)
        logger.info("Draft post created: %s", post.id)
        return post


async def schedule_post(post_id: str, scheduled_at: datetime) -> InstagramPost:
    """Move a draft post to 'scheduled' status."""
    from sqlalchemy import select

    async for db in get_db():
        post = (await db.execute(
            select(InstagramPost).where(InstagramPost.id == uuid.UUID(post_id))
        )).scalar_one_or_none()
        if not post:
            raise ValueError(f"Post {post_id} not found")

        post.status = PostStatus.scheduled
        post.scheduled_at = scheduled_at
        await db.commit()
        await db.refresh(post)
        logger.info("Post %s scheduled for %s", post_id, scheduled_at)
        return post


async def publish_post(post_id: str) -> InstagramPost:
    """
    Publish a post via Meta Graph API.

    Requires env vars:
      INSTAGRAM_ACCESS_TOKEN — long-lived page access token
      INSTAGRAM_ACCOUNT_ID  — Instagram Business Account ID
    """
    from sqlalchemy import select

    settings = get_settings()
    access_token = getattr(settings, "INSTAGRAM_ACCESS_TOKEN", "") or ""
    account_id = getattr(settings, "INSTAGRAM_ACCOUNT_ID", "") or ""

    async for db in get_db():
        post = (await db.execute(
            select(InstagramPost).where(InstagramPost.id == uuid.UUID(post_id))
        )).scalar_one_or_none()
        if not post:
            raise ValueError(f"Post {post_id} not found")

        if not access_token or not account_id:
            logger.warning("Instagram credentials not set — marking post as failed")
            post.status = PostStatus.failed
            await db.commit()
            return post

        full_caption = post.caption or ""
        if post.hashtags:
            full_caption += "\n\n" + " ".join(post.hashtags)

        try:
            ig_post_id = await _call_meta_api(
                account_id, access_token, full_caption, post.media_urls, post.post_type.value
            )
            post.status = PostStatus.posted
            post.instagram_post_id = ig_post_id
            post.posted_at = datetime.now(timezone.utc)
            logger.info("Post %s published → Instagram ID %s", post_id, ig_post_id)
        except Exception as exc:
            logger.error("Failed to publish post %s: %s", post_id, exc)
            post.status = PostStatus.failed

        await db.commit()
        await db.refresh(post)
        return post


async def publish_due_posts() -> int:
    """Publish all scheduled posts whose scheduled_at is now or in the past."""
    from sqlalchemy import select

    async for db in get_db():
        now = datetime.now(timezone.utc)
        due = (await db.execute(
            select(InstagramPost).where(
                InstagramPost.status == PostStatus.scheduled,
                InstagramPost.scheduled_at <= now,
            )
        )).scalars().all()

        count = 0
        for post in due:
            await publish_post(str(post.id))
            count += 1

        logger.info("Published %d due Instagram posts", count)
        return count

    return 0


async def _call_meta_api(
    account_id: str,
    access_token: str,
    caption: str,
    media_urls: list[str],
    post_type: str,
) -> str:
    """
    Call Meta Graph API to create and publish a media container.
    Returns the Instagram media ID.
    """
    import httpx

    base = f"https://graph.facebook.com/v19.0/{account_id}"

    if post_type == "carousel" and len(media_urls) > 1:
        # Step 1: create item containers
        item_ids = []
        async with httpx.AsyncClient() as client:
            for url in media_urls[:10]:
                r = await client.post(f"{base}/media", params={
                    "image_url": url,
                    "is_carousel_item": "true",
                    "access_token": access_token,
                })
                r.raise_for_status()
                item_ids.append(r.json()["id"])

            # Step 2: create carousel container
            r = await client.post(f"{base}/media", params={
                "media_type": "CAROUSEL",
                "caption": caption,
                "children": ",".join(item_ids),
                "access_token": access_token,
            })
            r.raise_for_status()
            container_id = r.json()["id"]

            # Step 3: publish
            r = await client.post(f"{base}/media_publish", params={
                "creation_id": container_id,
                "access_token": access_token,
            })
            r.raise_for_status()
            return r.json()["id"]
    else:
        # Single image/reel
        async with httpx.AsyncClient() as client:
            media_url = media_urls[0] if media_urls else ""
            params: dict[str, str] = {"caption": caption, "access_token": access_token}
            if post_type == "reel":
                params["media_type"] = "REELS"
                params["video_url"] = media_url
            else:
                params["image_url"] = media_url

            r = await client.post(f"{base}/media", params=params)
            r.raise_for_status()
            container_id = r.json()["id"]

            r = await client.post(f"{base}/media_publish", params={
                "creation_id": container_id,
                "access_token": access_token,
            })
            r.raise_for_status()
            return r.json()["id"]
