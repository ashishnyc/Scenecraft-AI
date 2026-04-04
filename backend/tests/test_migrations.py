"""Unit tests for migration structure (SC-2).

These tests verify the migration file is well-formed without needing
a live database. Integration tests (requiring PostgreSQL) are marked
with @pytest.mark.integration and skipped by default.
"""
import importlib
import pytest


def _load_migration():
    import glob, os
    versions_dir = os.path.join(os.path.dirname(__file__), "../alembic/versions")
    files = glob.glob(f"{versions_dir}/*_initial_schema.py")
    assert files, "Migration file not found"
    spec_name = os.path.basename(files[0]).replace(".py", "")
    spec = importlib.util.spec_from_file_location(spec_name, files[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_has_upgrade_and_downgrade():
    m = _load_migration()
    assert callable(m.upgrade)
    assert callable(m.downgrade)


def test_migration_has_revision_id():
    m = _load_migration()
    assert isinstance(m.revision, str) and len(m.revision) > 0


def test_migration_down_revision_is_none():
    """Initial migration must have no parent."""
    m = _load_migration()
    assert m.down_revision is None


EXPECTED_TABLES = [
    "workspaces",
    "characters",
    "projects",
    "character_castings",
    "tasks",
    "subtasks",
    "review_actions",
]

def test_upgrade_references_all_tables():
    import inspect
    m = _load_migration()
    source = inspect.getsource(m.upgrade)
    for table in EXPECTED_TABLES:
        assert f'"{table}"' in source, f"Table '{table}' not found in upgrade()"


def test_downgrade_drops_all_tables():
    import inspect
    m = _load_migration()
    source = inspect.getsource(m.downgrade)
    for table in EXPECTED_TABLES:
        assert table in source, f"Table '{table}' not dropped in downgrade()"


EXPECTED_ENUMS = [
    "roletype", "projecttype", "projectstatus",
    "castingrole", "castingstatus",
    "taskstatus", "subtasktype", "subtaskstatus", "reviewactiontype",
]

def test_upgrade_defines_all_enums():
    import inspect
    m = _load_migration()
    source = inspect.getsource(m.upgrade)
    for enum_name in EXPECTED_ENUMS:
        assert enum_name in source, f"Enum '{enum_name}' not found in upgrade()"
