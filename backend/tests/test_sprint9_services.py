"""Tests for Sprint 9 infrastructure and ops services (SA-48 through SA-54)."""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock


# ── SA-48: Temporal workflow ──────────────────────────────────────────────────

def test_temporal_workflow_importable():
    """Module should import cleanly even without temporalio installed."""
    from app.services.temporal_workflow import start_workflow, _TEMPORAL_AVAILABLE
    assert callable(start_workflow)


@pytest.mark.asyncio
async def test_temporal_start_workflow_no_temporal():
    """start_workflow returns None gracefully when temporalio is absent."""
    with patch("app.services.temporal_workflow._TEMPORAL_AVAILABLE", False):
        from app.services.temporal_workflow import start_workflow
        result = await start_workflow("task-1")
    assert result is None


# ── SA-49: GPU scheduler ──────────────────────────────────────────────────────

from app.services.gpu_scheduler import decide_route, JobRoute, _LOCAL_COST_PER_CLIP, _CLOUD_COST_PER_CLIP


def test_decide_route_no_gpu_goes_cloud():
    """When no local GPU is detected, route to cloud."""
    with patch("app.services.gpu_scheduler._query_local_gpu", return_value={}):
        decision = decide_route("clip_generation", 1)
    assert decision.route == JobRoute.cloud
    assert decision.estimated_cost == _CLOUD_COST_PER_CLIP


def test_decide_route_sufficient_vram_goes_local():
    """When local GPU has enough VRAM, route locally."""
    with patch("app.services.gpu_scheduler._query_local_gpu", return_value={
        "name": "NVIDIA L4", "free_mb": 20_000, "total_mb": 24_000, "utilization_pct": 10
    }), patch("app.services.gpu_scheduler._local_queue_depth", return_value=0):
        decision = decide_route("clip_generation", 1)
    assert decision.route == JobRoute.local
    assert decision.estimated_cost == _LOCAL_COST_PER_CLIP


def test_decide_route_full_queue_goes_cloud():
    """Even with enough VRAM, a full local queue forces cloud routing."""
    with patch("app.services.gpu_scheduler._query_local_gpu", return_value={
        "name": "NVIDIA L4", "free_mb": 20_000, "total_mb": 24_000, "utilization_pct": 50
    }), patch("app.services.gpu_scheduler._local_queue_depth", return_value=5):
        decision = decide_route("clip_generation", 1)
    assert decision.route == JobRoute.cloud


def test_decide_route_cost_scales_with_num_jobs():
    with patch("app.services.gpu_scheduler._query_local_gpu", return_value={}):
        decision = decide_route("clip_generation", 10)
    assert decision.estimated_cost == _CLOUD_COST_PER_CLIP * 10


# ── SA-50: Retry manager ──────────────────────────────────────────────────────

from app.services.retry_manager import record_clip_failure, get_failed_clips, clear_failures


@pytest.mark.asyncio
async def test_record_and_get_failed_clips():
    mock_row = MagicMock()
    mock_row.script = {}

    call_count = 0

    async def mock_get_db():
        nonlocal call_count
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_row
        db.execute = AsyncMock(return_value=result)
        db.add = MagicMock()
        db.commit = AsyncMock()
        yield db
        call_count += 1

    with patch("app.services.retry_manager.get_db", mock_get_db):
        await record_clip_failure("task-1", 3, "API timeout")

    assert mock_row.script["clip_failures"][0]["shot_index"] == 3
    assert mock_row.script["clip_failures"][0]["attempts"] == 1


@pytest.mark.asyncio
async def test_get_failed_clips_filters_exhausted():
    """Clips that hit MAX_RETRIES should not be returned."""
    mock_row = MagicMock()
    mock_row.script = {
        "clip_failures": [
            {"shot_index": 0, "error": "timeout", "attempts": 3},  # exhausted
            {"shot_index": 1, "error": "timeout", "attempts": 1},  # retryable
        ]
    }

    async def mock_get_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_row
        db.execute = AsyncMock(return_value=result)
        yield db

    with patch("app.services.retry_manager.get_db", mock_get_db):
        failures = await get_failed_clips("task-1")

    assert len(failures) == 1
    assert failures[0]["shot_index"] == 1


# ── SA-51: Asset lifecycle ────────────────────────────────────────────────────

from app.services.asset_lifecycle import _days_since
from datetime import datetime, timezone, timedelta


def test_days_since_past():
    past = datetime.now(timezone.utc) - timedelta(days=35)
    assert _days_since(past) >= 35


def test_days_since_now():
    assert _days_since(datetime.now(timezone.utc)) == 0


# ── SA-53: Cost tracker ───────────────────────────────────────────────────────

from app.services.cost_tracker import CostBreakdown, check_task_cost_alert


def test_cost_breakdown_to_dict():
    bd = CostBreakdown(
        task_id="t1",
        total=Decimal("4.25"),
        by_stage={"clip_generation": Decimal("3.50"), "audio_synthesis": Decimal("0.75")},
    )
    d = bd.to_dict()
    assert d["total_usd"] == "4.25"
    assert d["by_stage"]["clip_generation"] == "3.50"


@pytest.mark.asyncio
async def test_check_task_cost_alert_under_threshold():
    mock_row = MagicMock()
    mock_row.script = {"cost_breakdown": {"clip_generation": "1.00"}}
    mock_row.total_cost_usd = Decimal("1.00")

    async def mock_get_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_row
        db.execute = AsyncMock(return_value=result)
        yield db

    with patch("app.services.cost_tracker.get_db", mock_get_db):
        alerts = await check_task_cost_alert("task-1")
    assert alerts == []


@pytest.mark.asyncio
async def test_check_task_cost_alert_over_threshold():
    mock_row = MagicMock()
    mock_row.script = {"cost_breakdown": {"clip_generation": "15.00"}}
    mock_row.total_cost_usd = Decimal("15.00")

    async def mock_get_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_row
        db.execute = AsyncMock(return_value=result)
        yield db

    with patch("app.services.cost_tracker.get_db", mock_get_db):
        alerts = await check_task_cost_alert("task-1")
    assert len(alerts) == 1
    assert "threshold" in alerts[0]


# ── SA-54: Security ───────────────────────────────────────────────────────────

from app.core.security import sanitise_string, sanitise_dict


def test_sanitise_string_strips_null_bytes():
    assert "\x00" not in sanitise_string("hello\x00world")


def test_sanitise_string_strips_control_chars():
    result = sanitise_string("clean\x01dirty\x1ftext")
    assert "\x01" not in result
    assert "\x1f" not in result
    assert "cleantext" in result.replace("dirty", "")


def test_sanitise_string_enforces_max_length():
    assert len(sanitise_string("x" * 20_000, max_length=100)) == 100


def test_sanitise_dict_recursive():
    data = {"key": "val\x00ue", "nested": {"inner": "ok\x01"}}
    result = sanitise_dict(data)
    assert "\x00" not in result["key"]
    assert "\x01" not in result["nested"]["inner"]


def test_validate_secrets_weak_key():
    from app.core.security import validate_secrets_at_startup
    mock_settings = MagicMock()
    mock_settings.SECRET_KEY = "secret"
    mock_settings.DEV_AUTO_LOGIN = False
    mock_settings.DEBUG = False
    mock_settings.ANTHROPIC_API_KEY = "sk-test"

    with patch("app.core.security.get_settings", return_value=mock_settings):
        warnings = validate_secrets_at_startup()
    assert any("placeholder" in w.lower() or "short" in w.lower() for w in warnings)
