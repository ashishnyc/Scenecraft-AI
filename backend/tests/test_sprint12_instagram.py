"""Sprint 12 tests — Instagram pipeline (SA-65–67)."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── SA-65: Post generation ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_post_content_no_api_key():
    """Falls back to placeholder when ANTHROPIC_API_KEY not set."""
    from app.services.instagram_pipeline import generate_post_content

    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = ""

    with patch("app.services.instagram_pipeline.get_settings", return_value=mock_settings):
        result = await generate_post_content("ws-1", None, "A stormy evening at the manor.", "image")

    assert result["caption"] == "A stormy evening at the manor."
    assert isinstance(result["hashtags"], list)


@pytest.mark.asyncio
async def test_generate_post_content_with_api_key():
    """Returns AI-generated caption when API key is set."""
    from app.services.instagram_pipeline import generate_post_content
    import json

    mock_settings = MagicMock()
    mock_settings.ANTHROPIC_API_KEY = "sk-test"

    payload = {"caption": "Dark skies over the manor.", "hashtags": ["#mystery"], "alt_text": "A stormy manor"}
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=json.dumps(payload))]
    )

    with patch("app.services.instagram_pipeline.get_settings", return_value=mock_settings), \
         patch("app.services.instagram_pipeline.get_db", return_value=_empty_db_gen()), \
         patch("anthropic.Anthropic", return_value=mock_client):
        result = await generate_post_content("ws-1", None, "A stormy manor", "image")

    assert result["caption"] == "Dark skies over the manor."
    assert "#mystery" in result["hashtags"]


# ── SA-65: Schedule + publish ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_post():
    """schedule_post updates status to 'scheduled'."""
    from app.services.instagram_pipeline import schedule_post
    from app.models.instagram import InstagramPost, PostStatus
    from datetime import datetime, timezone

    mock_post = MagicMock(spec=InstagramPost)
    mock_post.status = PostStatus.draft

    async def mock_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_post
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        yield db

    scheduled_time = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    with patch("app.services.instagram_pipeline.get_db", mock_db):
        post = await schedule_post(str(uuid.uuid4()), scheduled_time)

    assert mock_post.status == PostStatus.scheduled
    assert mock_post.scheduled_at == scheduled_time


@pytest.mark.asyncio
async def test_publish_post_no_credentials():
    """publish_post marks post as failed when Instagram credentials not set."""
    from app.services.instagram_pipeline import publish_post
    from app.models.instagram import InstagramPost, PostStatus, PostType

    mock_post = MagicMock(spec=InstagramPost)
    mock_post.status = PostStatus.scheduled
    mock_post.post_type = PostType.image
    mock_post.caption = "Test caption"
    mock_post.hashtags = []
    mock_post.media_urls = []
    mock_post.instagram_post_id = None

    mock_settings = MagicMock()
    mock_settings.INSTAGRAM_ACCESS_TOKEN = ""
    mock_settings.INSTAGRAM_ACCOUNT_ID = ""

    async def mock_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_post
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        yield db

    with patch("app.services.instagram_pipeline.get_db", mock_db), \
         patch("app.services.instagram_pipeline.get_settings", return_value=mock_settings):
        post = await publish_post(str(uuid.uuid4()))

    assert mock_post.status == PostStatus.failed


# ── SA-66: Safety checks ──────────────────────────────────────────────────────

def test_safety_check_passes_clean_reply():
    from app.services.instagram_replies import _safety_check
    result = _safety_check("Thanks so much for your kind words!")
    assert result["passed"] is True
    assert result["reasons"] == []


def test_safety_check_fails_too_long():
    from app.services.instagram_replies import _safety_check
    reply = "A" * 200
    result = _safety_check(reply)
    assert result["passed"] is False
    assert any("too_long" in r for r in result["reasons"])


def test_safety_check_fails_toxicity():
    from app.services.instagram_replies import _safety_check
    result = _safety_check("You are so stupid for asking that")
    assert result["passed"] is False
    assert any("toxicity" in r for r in result["reasons"])


def test_is_spam_detects_f4f():
    from app.services.instagram_replies import _is_spam
    assert _is_spam("f4f follow me back!") is True


def test_is_spam_passes_genuine():
    from app.services.instagram_replies import _is_spam
    assert _is_spam("Love this scene so much!") is False


@pytest.mark.asyncio
async def test_generate_reply_spam_blocked():
    """Spam comments are rejected without calling the LLM."""
    from app.services.instagram_replies import generate_reply
    from app.models.instagram import InstagramComment, CommentReplyStatus

    mock_comment = MagicMock(spec=InstagramComment)
    mock_comment.text = "follow for follow check my profile"
    mock_comment.reply_status = CommentReplyStatus.pending

    async def mock_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_comment
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()
        yield db

    with patch("app.services.instagram_replies.get_db", mock_db):
        result = await generate_reply(str(uuid.uuid4()))

    assert result is None
    assert mock_comment.reply_status == CommentReplyStatus.rejected


# ── SA-66: post_reply ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_reply_no_credentials():
    """post_reply returns False when INSTAGRAM_ACCESS_TOKEN not set."""
    from app.services.instagram_replies import post_reply
    from app.models.instagram import InstagramComment, CommentReplyStatus

    mock_comment = MagicMock(spec=InstagramComment)
    mock_comment.reply_status = CommentReplyStatus.approved
    mock_comment.generated_reply = "Thanks for the support!"
    mock_comment.instagram_comment_id = "ig-comment-123"

    mock_settings = MagicMock()
    mock_settings.INSTAGRAM_ACCESS_TOKEN = ""

    async def mock_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_comment
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()
        yield db

    with patch("app.services.instagram_replies.get_db", mock_db), \
         patch("app.services.instagram_replies.get_settings", return_value=mock_settings):
        result = await post_reply(str(uuid.uuid4()))

    assert result is False


# ── SA-67: Model integrity ────────────────────────────────────────────────────

def test_instagram_post_model_fields():
    from app.models.instagram import InstagramPost, PostStatus, PostType
    assert hasattr(InstagramPost, "caption")
    assert hasattr(InstagramPost, "hashtags")
    assert hasattr(InstagramPost, "scheduled_at")
    assert hasattr(InstagramPost, "instagram_post_id")


def test_instagram_comment_model_fields():
    from app.models.instagram import InstagramComment, CommentReplyStatus
    assert hasattr(InstagramComment, "generated_reply")
    assert hasattr(InstagramComment, "safety_flags")
    assert hasattr(InstagramComment, "reply_status")


def test_post_status_enum():
    from app.models.instagram import PostStatus
    assert PostStatus.draft.value == "draft"
    assert PostStatus.scheduled.value == "scheduled"
    assert PostStatus.posted.value == "posted"
    assert PostStatus.failed.value == "failed"


def test_comment_reply_status_enum():
    from app.models.instagram import CommentReplyStatus
    assert CommentReplyStatus.pending.value == "pending"
    assert CommentReplyStatus.approved.value == "approved"
    assert CommentReplyStatus.posted.value == "posted"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _empty_db_gen():
    """Async generator that yields nothing — simulates no character found."""
    return
    yield  # make it a generator
