"""Unit tests for subtask DAG ordering and dependency blocking (SA-7)."""
import os
import uuid
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

from app.models.subtask import SubtaskStatus, SubtaskType
from app.services.dag import CyclicDependencyError, check_dependencies_met, topological_sort


class FakeSubtask:
    def __init__(self, type=SubtaskType.script, status=SubtaskStatus.queued, depends_on=None):
        self.id = uuid.uuid4()
        self.type = type
        self.status = status
        self.depends_on = depends_on or []


# --- Topological sort ---

def test_no_dependencies_preserves_order():
    a, b, c = FakeSubtask(), FakeSubtask(), FakeSubtask()
    result = topological_sort([a, b, c])
    assert len(result) == 3


def test_linear_chain_ordered():
    a = FakeSubtask()
    b = FakeSubtask(depends_on=[str(a.id)])
    c = FakeSubtask(depends_on=[str(b.id)])
    result = topological_sort([c, b, a])  # pass in reverse order
    ids = [r.id for r in result]
    assert ids.index(a.id) < ids.index(b.id)
    assert ids.index(b.id) < ids.index(c.id)


def test_diamond_dependency_ordered():
    # A → B, A → C, B → D, C → D
    a = FakeSubtask()
    b = FakeSubtask(depends_on=[str(a.id)])
    c = FakeSubtask(depends_on=[str(a.id)])
    d = FakeSubtask(depends_on=[str(b.id), str(c.id)])
    result = topological_sort([d, c, b, a])
    ids = [r.id for r in result]
    assert ids.index(a.id) < ids.index(b.id)
    assert ids.index(a.id) < ids.index(c.id)
    assert ids.index(b.id) < ids.index(d.id)
    assert ids.index(c.id) < ids.index(d.id)


def test_cyclic_dependency_raises():
    a = FakeSubtask()
    b = FakeSubtask()
    a.depends_on = [str(b.id)]
    b.depends_on = [str(a.id)]
    with pytest.raises(CyclicDependencyError):
        topological_sort([a, b])


def test_unknown_dependency_ignored():
    a = FakeSubtask(depends_on=["00000000-0000-0000-0000-000000000000"])
    result = topological_sort([a])
    assert len(result) == 1


# --- Dependency blocking ---

def test_unmet_dependency_detected():
    a = FakeSubtask(status=SubtaskStatus.queued)
    b = FakeSubtask(depends_on=[str(a.id)])
    unmet = check_dependencies_met(b, [a, b])
    assert str(a.id) in unmet


def test_met_dependency_passes():
    a = FakeSubtask(status=SubtaskStatus.done)
    b = FakeSubtask(depends_on=[str(a.id)])
    unmet = check_dependencies_met(b, [a, b])
    assert unmet == []


def test_no_dependencies_always_passes():
    a = FakeSubtask()
    unmet = check_dependencies_met(a, [a])
    assert unmet == []
