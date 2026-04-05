"""Sprint 11 tests — Talent Roster (SA-60–64)."""
import uuid
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


# ── SA-60: Character CRUD ─────────────────────────────────────────────────────

def test_character_response_schema_includes_new_fields():
    """CharacterResponse includes visual_references, appearance_state, engagement_stats."""
    from app.schemas.character import CharacterResponse
    fields = CharacterResponse.model_fields
    assert "visual_references" in fields
    assert "appearance_state" in fields
    assert "engagement_stats" in fields
    assert "created_at" in fields


def test_character_create_schema_voice_profile():
    """CharacterCreate accepts voice_profile_id."""
    from app.schemas.character import CharacterCreate
    from app.models.character import RoleType
    obj = CharacterCreate(name="Alex", role_type=RoleType.lead, voice_profile_id="el-123")
    assert obj.voice_profile_id == "el-123"


def test_character_update_schema_lora():
    """CharacterUpdate accepts lora_model_url."""
    from app.schemas.character import CharacterUpdate
    obj = CharacterUpdate(lora_model_url="s3://bucket/model.safetensors")
    assert obj.lora_model_url == "s3://bucket/model.safetensors"


# ── SA-61: Visual identity ────────────────────────────────────────────────────

def test_appearance_version_create_schema():
    """AppearanceVersionCreate validates label."""
    from app.schemas.character import AppearanceVersionCreate
    v = AppearanceVersionCreate(label="Season 2", description="Post-arc look")
    assert v.label == "Season 2"
    assert v.description == "Post-arc look"
    assert v.image_url is None


def test_appearance_version_label_required():
    from app.schemas.character import AppearanceVersionCreate
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        AppearanceVersionCreate(label="")


# ── SA-62: Casting schemas ────────────────────────────────────────────────────

def test_casting_create_schema():
    from app.schemas.character import CastingCreate
    from app.models.character import CastingRole
    char_id = uuid.uuid4()
    obj = CastingCreate(character_id=char_id, role=CastingRole.lead, character_arc_notes="Hero journey")
    assert obj.character_id == char_id
    assert obj.role == CastingRole.lead
    assert obj.character_arc_notes == "Hero journey"


def test_casting_update_schema():
    from app.schemas.character import CastingUpdate
    from app.models.character import CastingRole, CastingStatus
    obj = CastingUpdate(role=CastingRole.recurring, status=CastingStatus.written_out)
    assert obj.role == CastingRole.recurring
    assert obj.status == CastingStatus.written_out


def test_casting_response_schema_has_character():
    from app.schemas.character import CastingResponse
    assert "character" in CastingResponse.model_fields


# ── SA-64: Character analytics ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compute_character_analytics_no_tasks():
    """Returns zeros for a character with no published videos."""
    from app.services.character_analytics import compute_character_analytics
    from app.models.character import Character, RoleType
    import uuid

    char_id = uuid.uuid4()
    mock_char = MagicMock(spec=Character)
    mock_char.id = char_id
    mock_char.name = "Alex"
    mock_char.engagement_stats = {}

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_char)

    # No castings
    castings_result = MagicMock()
    castings_result.scalars.return_value.all.return_value = []
    # No tasks
    tasks_result = MagicMock()
    tasks_result.scalars.return_value.all.return_value = []

    mock_db.execute = AsyncMock(side_effect=[castings_result, tasks_result])

    result = await compute_character_analytics(char_id, mock_db)

    assert result.total_appearances == 0
    assert result.total_views == 0
    assert result.avg_views_per_appearance == 0.0
    assert result.top_project_id is None


@pytest.mark.asyncio
async def test_compute_character_analytics_with_views():
    """Correctly aggregates views from tasks with matching cast name."""
    from app.services.character_analytics import compute_character_analytics
    from app.models.character import Character, CharacterCasting

    char_id = uuid.uuid4()
    project_id = uuid.uuid4()

    mock_char = MagicMock(spec=Character)
    mock_char.id = char_id
    mock_char.name = "Alex"
    mock_char.engagement_stats = {}

    mock_casting = MagicMock(spec=CharacterCasting)
    mock_casting.project_id = project_id
    mock_casting.character_id = char_id

    mock_task = MagicMock()
    mock_task.project_id = project_id
    mock_task.youtube_video_id = "yt-123"
    mock_task.script = {
        "cast": ["Alex", "Sam"],
        "performance_metrics": {"view_count": 5000},
    }

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_char)

    castings_result = MagicMock()
    castings_result.scalars.return_value.all.return_value = [mock_casting]

    project_tasks_result = MagicMock()
    project_tasks_result.scalars.return_value.all.return_value = [mock_task]

    all_tasks_result = MagicMock()
    all_tasks_result.scalars.return_value.all.return_value = []

    mock_db.execute = AsyncMock(side_effect=[castings_result, project_tasks_result, all_tasks_result])

    result = await compute_character_analytics(char_id, mock_db)

    assert result.total_views == 5000
    assert result.total_appearances == 1
    assert result.avg_views_per_appearance == 5000.0
    assert result.top_project_id == str(project_id)


def test_extract_views_direct():
    from app.services.character_analytics import _extract_views
    assert _extract_views({"view_count": 1234}) == 1234


def test_extract_views_nested_statistics():
    from app.services.character_analytics import _extract_views
    assert _extract_views({"statistics": {"viewCount": "9999"}}) == 9999


def test_extract_views_empty():
    from app.services.character_analytics import _extract_views
    assert _extract_views({}) == 0


def test_extract_views_retention_curve():
    from app.services.character_analytics import _extract_views
    metrics = {"retention_curve": [{"cumulative_views": 100}, {"cumulative_views": 500}]}
    assert _extract_views(metrics) == 500


# ── SA-63: CharacterAnalytics schema ─────────────────────────────────────────

def test_character_analytics_schema():
    from app.schemas.character import CharacterAnalytics
    obj = CharacterAnalytics(
        character_id=uuid.uuid4(),
        name="Alex",
        total_appearances=3,
        total_views=15000,
        avg_views_per_appearance=5000.0,
        top_project_id="proj-1",
        engagement_breakdown={"proj-1": 15000},
    )
    assert obj.total_views == 15000
    assert obj.engagement_breakdown["proj-1"] == 15000
