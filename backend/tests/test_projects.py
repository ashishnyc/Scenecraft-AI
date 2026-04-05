"""Unit tests for project schemas and validation (SA-5)."""
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

from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.models.project import ProjectType, ProjectStatus


# --- ProjectCreate ---

def test_create_serialised_minimal():
    p = ProjectCreate(name="My Series", type="serialised")
    assert p.type == ProjectType.serialised
    assert p.story_bible is None


def test_create_anthology():
    p = ProjectCreate(name="Standalone", type="anthology")
    assert p.type == ProjectType.anthology


def test_create_invalid_type_rejected():
    with pytest.raises(Exception):
        ProjectCreate(name="Bad", type="unknown")


def test_create_serialised_valid_story_bible():
    p = ProjectCreate(
        name="Epic",
        type="serialised",
        story_bible={"characters": [], "plot_threads": [], "timeline": []},
    )
    assert p.story_bible is not None


def test_create_serialised_incomplete_story_bible_rejected():
    with pytest.raises(Exception, match="story_bible"):
        ProjectCreate(
            name="Epic",
            type="serialised",
            story_bible={"characters": []},  # missing plot_threads and timeline
        )


def test_create_anthology_no_story_bible_validation():
    # anthology type doesn't enforce story_bible keys
    p = ProjectCreate(name="Ep1", type="anthology", story_bible={"anything": "goes"})
    assert p.story_bible == {"anything": "goes"}


def test_create_episode_count_must_be_positive():
    with pytest.raises(Exception):
        ProjectCreate(name="Series", type="serialised", episode_count=0)


# --- ProjectUpdate ---

def test_update_all_optional():
    u = ProjectUpdate()
    assert u.name is None
    assert u.status is None


def test_update_status():
    u = ProjectUpdate(status="paused")
    assert u.status == ProjectStatus.paused


def test_update_exclude_none():
    u = ProjectUpdate(name="New Name")
    data = u.model_dump(exclude_none=True)
    assert list(data.keys()) == ["name"]


# --- ProjectResponse ---

def test_response_from_attributes():
    import uuid
    class FakeProject:
        id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        name = "Test"
        type = ProjectType.serialised
        story_bible = None
        status = ProjectStatus.active
        episode_count = None

    r = ProjectResponse.model_validate(FakeProject())
    assert r.name == "Test"
    assert r.type == ProjectType.serialised
