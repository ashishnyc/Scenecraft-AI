"""Unit tests for task lifecycle state machine (SA-6)."""
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

from app.models.task import TaskStatus
from app.services.state_machine import (
    VALID_TRANSITIONS,
    InvalidTransitionError,
    TransitionGuardError,
    validate_transition,
)


class FakeTask:
    """Minimal Task-like object for testing guards."""
    def __init__(self, concept_brief=None):
        self.concept_brief = concept_brief


# --- Valid transitions ---

VALID_SEQUENCE = [
    (TaskStatus.idea, TaskStatus.approved),
    (TaskStatus.approved, TaskStatus.scripting),
    (TaskStatus.scripting, TaskStatus.audio_preview),
    (TaskStatus.audio_preview, TaskStatus.script_review),
    (TaskStatus.script_review, TaskStatus.producing),
    (TaskStatus.producing, TaskStatus.final_review),
    (TaskStatus.final_review, TaskStatus.scheduled),
    (TaskStatus.scheduled, TaskStatus.published),
]


@pytest.mark.parametrize("current,target", VALID_SEQUENCE)
def test_valid_transition(current, target):
    task = FakeTask(concept_brief="some brief")
    validate_transition(current, target, task)  # should not raise


# --- Invalid transitions (skipping states) ---

INVALID_TRANSITIONS = [
    (TaskStatus.idea, TaskStatus.scripting),
    (TaskStatus.idea, TaskStatus.published),
    (TaskStatus.approved, TaskStatus.idea),
    (TaskStatus.scripting, TaskStatus.approved),
    (TaskStatus.published, TaskStatus.scheduled),
    (TaskStatus.published, TaskStatus.idea),
    (TaskStatus.final_review, TaskStatus.idea),
]


@pytest.mark.parametrize("current,target", INVALID_TRANSITIONS)
def test_invalid_transition_raises(current, target):
    task = FakeTask(concept_brief="brief")
    with pytest.raises(InvalidTransitionError):
        validate_transition(current, target, task)


# --- Terminal state ---

def test_published_is_terminal():
    task = FakeTask(concept_brief="brief")
    with pytest.raises(InvalidTransitionError):
        validate_transition(TaskStatus.published, TaskStatus.published, task)


# --- Guards ---

def test_approve_without_concept_brief_raises():
    task = FakeTask(concept_brief=None)
    with pytest.raises(TransitionGuardError, match="concept_brief"):
        validate_transition(TaskStatus.idea, TaskStatus.approved, task)


def test_approve_with_concept_brief_passes():
    task = FakeTask(concept_brief="This video is about X")
    validate_transition(TaskStatus.idea, TaskStatus.approved, task)  # should not raise


# --- Completeness: every status has an entry in VALID_TRANSITIONS ---

def test_all_statuses_covered():
    for s in TaskStatus:
        assert s in VALID_TRANSITIONS, f"{s} missing from VALID_TRANSITIONS"
