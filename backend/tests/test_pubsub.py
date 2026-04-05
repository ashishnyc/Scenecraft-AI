"""Unit tests for the pub/sub event publishing service."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_publish_task_event_sends_correct_payload():
    """publish_task_event should publish a JSON payload with the right keys."""
    mock_redis = AsyncMock()

    with patch("app.services.pubsub.get_redis", return_value=mock_redis):
        from app.services.pubsub import publish_task_event, CHANNEL

        await publish_task_event(
            task_id="task-123",
            status="approved",
            workspace_id="ws-456",
        )

    mock_redis.publish.assert_awaited_once()
    channel_arg, payload_arg = mock_redis.publish.call_args.args
    assert channel_arg == CHANNEL

    data = json.loads(payload_arg)
    assert data["type"] == "task_status"
    assert data["task_id"] == "task-123"
    assert data["status"] == "approved"
    assert data["workspace_id"] == "ws-456"


@pytest.mark.asyncio
async def test_publish_task_event_uses_correct_channel():
    """publish_task_event should always use the CHANNEL constant."""
    mock_redis = AsyncMock()

    with patch("app.services.pubsub.get_redis", return_value=mock_redis):
        from app.services.pubsub import publish_task_event, CHANNEL

        await publish_task_event("t1", "scripting", "w1")

    channel_used = mock_redis.publish.call_args.args[0]
    assert channel_used == CHANNEL
    assert CHANNEL == "task_events"
