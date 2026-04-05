"""WebSocket endpoint for real-time task status events."""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db.redis import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

CHANNEL = "task_events"
PING_INTERVAL = 25  # seconds


@router.websocket("/ws/events")
async def events_websocket(websocket: WebSocket):
    await websocket.accept()

    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL)

    # Ping task keeps connection alive through proxies
    async def ping_loop():
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                return

    ping_task = asyncio.create_task(ping_loop())

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                await websocket.send_json(data)
            except Exception as exc:
                logger.warning("WS send error: %s", exc)
                break
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        ping_task.cancel()
        await pubsub.unsubscribe(CHANNEL)
        await pubsub.aclose()
