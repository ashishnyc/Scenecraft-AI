"""Redis pub/sub helpers for real-time task status events."""
import json
from app.db.redis import get_redis

CHANNEL = "task_events"


async def publish_task_event(
    task_id: str,
    status: str,
    workspace_id: str,
) -> None:
    """Publish a task status-change event to the Redis channel."""
    redis = get_redis()
    payload = json.dumps({
        "type": "task_status",
        "task_id": task_id,
        "status": status,
        "workspace_id": workspace_id,
    })
    await redis.publish(CHANNEL, payload)
