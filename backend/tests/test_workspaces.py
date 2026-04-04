"""Unit tests for workspace schemas and route logic (SA-4).

No live database required — tests focus on Pydantic schema validation.
"""
import os
import pytest

os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("S3_BUCKET", "test")
os.environ.setdefault("SECRET_KEY", "supersecrettestkey1234567890abcdef")

from app.schemas.workspace import WorkspaceCreate, WorkspaceUpdate, WorkspaceResponse


# --- WorkspaceCreate ---

def test_create_schema_minimal():
    w = WorkspaceCreate(name="My Channel")
    assert w.name == "My Channel"
    assert w.youtube_channel_id is None
    assert w.style_guide is None


def test_create_schema_full():
    w = WorkspaceCreate(
        name="My Channel",
        youtube_channel_id="UC123",
        style_guide={"tone": "casual"},
        upload_schedule={"day": "monday"},
        competitor_channels=["UC456", "UC789"],
    )
    assert w.youtube_channel_id == "UC123"
    assert w.style_guide == {"tone": "casual"}
    assert len(w.competitor_channels) == 2


def test_create_schema_empty_name_rejected():
    with pytest.raises(Exception):
        WorkspaceCreate(name="")


def test_create_schema_name_too_long_rejected():
    with pytest.raises(Exception):
        WorkspaceCreate(name="x" * 256)


# --- WorkspaceUpdate ---

def test_update_schema_all_optional():
    u = WorkspaceUpdate()
    assert u.name is None
    assert u.style_guide is None


def test_update_schema_partial():
    u = WorkspaceUpdate(style_guide={"tone": "professional"})
    assert u.style_guide == {"tone": "professional"}
    assert u.name is None


def test_update_schema_exclude_none():
    u = WorkspaceUpdate(name="New Name")
    data = u.model_dump(exclude_none=True)
    assert "name" in data
    assert "style_guide" not in data


# --- WorkspaceResponse ---

def test_response_schema_from_attributes():
    import uuid
    from datetime import datetime, timezone

    class FakeWorkspace:
        id = uuid.uuid4()
        name = "Test"
        youtube_channel_id = "UC123"
        style_guide = None
        upload_schedule = None
        competitor_channels = None
        created_at = datetime.now(timezone.utc)

    r = WorkspaceResponse.model_validate(FakeWorkspace())
    assert r.name == "Test"
    assert r.youtube_channel_id == "UC123"
