"""Temporal worker entry point (SA-48).

Run with:
    python -m app.services.temporal_worker

Registers all activity functions and the VideoProductionWorkflow with
a Temporal worker connected to TEMPORAL_HOST (default: localhost:7233).
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


async def main() -> None:
    try:
        from temporalio.client import Client
        from temporalio.worker import Worker
    except ImportError:
        logger.error("temporalio package not installed. Run: pip install temporalio")
        return

    from app.services.temporal_workflow import (
        VideoProductionWorkflow,
        activity_run_outline,
        activity_run_audio,
        activity_run_video,
        activity_run_publish,
        activity_wait_for_gate,
    )

    temporal_host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    client = await Client.connect(temporal_host)

    worker = Worker(
        client,
        task_queue="video-production",
        workflows=[VideoProductionWorkflow],
        activities=[
            activity_run_outline,
            activity_run_audio,
            activity_run_video,
            activity_run_publish,
            activity_wait_for_gate,
        ],
    )

    logger.info("Temporal worker starting on queue 'video-production' → %s", temporal_host)
    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
