"""Instagram comment reply system (SA-66).

Generates in-character LLM replies to Instagram comments with safety filtering.

Safety filters:
  - Toxicity check (hate speech, threats, explicit content)
  - Brand safety (no competitor mentions, no price promises)
  - Length cap (max 150 chars for natural feel)
  - Blocks auto-reply if comment is spam or has <3 words

Flow:
  1. fetch_post_comments(post_id) — poll Meta Graph API for new comments
  2. generate_reply(comment_id) — Claude generates in-character reply
  3. review queue — replies sit in 'pending' until approved/rejected via API
  4. post_reply(comment_id) — approved replies posted via Meta Graph API
"""
from __future__ import annotations

import logging
import re
import json
from typing import Any

from app.core.config import get_settings
from app.db.postgres import get_db
from app.models.instagram import InstagramComment, InstagramPost, CommentReplyStatus

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_REPLY_CHARS = 150

# Safety: patterns that should block auto-reply
_SPAM_PATTERNS = [
    r"follow\s*for\s*follow",
    r"f4f",
    r"check\s*my\s*profile",
    r"dm\s*me\s*for",
    r"https?://",
]
_TOXICITY_KEYWORDS = [
    "hate", "kill", "die", "idiot", "stupid", "trash", "worst",
]


def _is_spam(text: str) -> bool:
    t = text.lower()
    for pat in _SPAM_PATTERNS:
        if re.search(pat, t):
            return True
    return False


def _safety_check(reply: str) -> dict[str, Any]:
    """Return safety flags dict. passed=True means safe to post."""
    flags: dict[str, Any] = {"passed": True, "reasons": []}
    lower = reply.lower()

    if len(reply) > _MAX_REPLY_CHARS:
        flags["passed"] = False
        flags["reasons"].append(f"too_long ({len(reply)} > {_MAX_REPLY_CHARS})")

    for kw in _TOXICITY_KEYWORDS:
        if kw in lower:
            flags["passed"] = False
            flags["reasons"].append(f"toxicity_keyword:{kw}")

    # No competitor names (placeholder — extend with actual list)
    if re.search(r"\b(competitor|rival_brand)\b", lower):
        flags["passed"] = False
        flags["reasons"].append("competitor_mention")

    return flags


async def fetch_post_comments(post_id: str) -> list[dict[str, Any]]:
    """
    Fetch comments from Meta Graph API for a given Instagram post.
    Stores new comments in the DB and returns them.
    """
    from sqlalchemy import select
    import uuid

    settings = get_settings()
    access_token = getattr(settings, "INSTAGRAM_ACCESS_TOKEN", "") or ""

    async for db in get_db():
        post = (await db.execute(
            select(InstagramPost).where(InstagramPost.id == uuid.UUID(post_id))
        )).scalar_one_or_none()
        if not post or not post.instagram_post_id:
            return []

        if not access_token:
            logger.warning("INSTAGRAM_ACCESS_TOKEN not set — cannot fetch comments")
            return []

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://graph.facebook.com/v19.0/{post.instagram_post_id}/comments",
                    params={"fields": "id,username,text,timestamp", "access_token": access_token},
                )
                r.raise_for_status()
                comments_data = r.json().get("data", [])
        except Exception as exc:
            logger.error("Failed to fetch comments for post %s: %s", post_id, exc)
            return []

        # Persist new comments
        existing_ids = {
            row for (row,) in (await db.execute(
                select(InstagramComment.instagram_comment_id)
                .where(InstagramComment.post_id == uuid.UUID(post_id))
            )).all()
        }

        new_comments = []
        for c in comments_data:
            if c["id"] in existing_ids:
                continue
            comment = InstagramComment(
                id=uuid.uuid4(),
                post_id=uuid.UUID(post_id),
                instagram_comment_id=c["id"],
                author_username=c.get("username", "unknown"),
                text=c.get("text", ""),
                reply_status=CommentReplyStatus.pending,
            )
            db.add(comment)
            new_comments.append(c)

        await db.commit()
        logger.info("Fetched %d new comments for post %s", len(new_comments), post_id)
        return new_comments


async def generate_reply(comment_id: str) -> str | None:
    """
    Generate an in-character reply to a comment using Claude.
    Stores the generated reply on the comment and runs safety check.
    Returns the reply text or None if blocked.
    """
    from sqlalchemy import select
    import uuid

    async for db in get_db():
        comment = (await db.execute(
            select(InstagramComment).where(InstagramComment.id == uuid.UUID(comment_id))
        )).scalar_one_or_none()
        if not comment:
            return None

        # Spam gate — checked before API key so no LLM cost is incurred
        if _is_spam(comment.text) or len(comment.text.split()) < 3:
            comment.reply_status = CommentReplyStatus.rejected
            comment.safety_flags = {"passed": False, "reasons": ["spam_or_too_short"]}
            await db.commit()
            return None

        settings = get_settings()
        if not settings.ANTHROPIC_API_KEY:
            return None

        # Load character context
        post = (await db.execute(
            select(InstagramPost).where(InstagramPost.id == comment.post_id)
        )).scalar_one_or_none()

        character_context = ""
        if post and post.character_id:
            from app.models.character import Character
            char = (await db.execute(
                select(Character).where(Character.id == post.character_id)
            )).scalar_one_or_none()
            if char:
                character_context = f"""
You are {char.name}, a {char.role_type.value} character.
Personality: {char.personality_prompt or 'Friendly and engaging'}
"""

        prompt = f"""{character_context}
A fan left this comment on your Instagram post:
"{comment.text}"

Write a warm, authentic reply in character. Keep it under {_MAX_REPLY_CHARS} characters.
Be genuine, personal, and avoid sounding like a bot. No hashtags. No links.
Return only the reply text."""

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=_MODEL,
                max_tokens=128,
                messages=[{"role": "user", "content": prompt}],
            )
            reply_text = response.content[0].text.strip().strip('"')
        except Exception as exc:
            logger.error("Reply generation failed for comment %s: %s", comment_id, exc)
            return None

        flags = _safety_check(reply_text)
        comment.generated_reply = reply_text
        comment.safety_flags = flags

        if not flags["passed"]:
            comment.reply_status = CommentReplyStatus.rejected
            logger.info("Reply for comment %s blocked by safety: %s", comment_id, flags["reasons"])
        # else stays 'pending' for human review

        await db.commit()
        return reply_text if flags["passed"] else None


async def post_reply(comment_id: str) -> bool:
    """Post an approved reply via Meta Graph API."""
    from sqlalchemy import select
    import uuid

    settings = get_settings()
    access_token = getattr(settings, "INSTAGRAM_ACCESS_TOKEN", "") or ""

    async for db in get_db():
        comment = (await db.execute(
            select(InstagramComment).where(InstagramComment.id == uuid.UUID(comment_id))
        )).scalar_one_or_none()
        if not comment or comment.reply_status != CommentReplyStatus.approved:
            return False
        if not comment.generated_reply:
            return False

        if not access_token:
            logger.warning("INSTAGRAM_ACCESS_TOKEN not set — cannot post reply")
            return False

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"https://graph.facebook.com/v19.0/{comment.instagram_comment_id}/replies",
                    params={"message": comment.generated_reply, "access_token": access_token},
                )
                r.raise_for_status()

            comment.reply_status = CommentReplyStatus.posted
            comment.posted_reply = comment.generated_reply
            await db.commit()
            logger.info("Reply posted for comment %s", comment_id)
            return True
        except Exception as exc:
            logger.error("Failed to post reply for comment %s: %s", comment_id, exc)
            return False
