"""Story bible management for serialised projects (SA-23).

The story bible tracks continuity across episodes: character states, open and
resolved plot threads, world-building rules, and a rolling episode log.

Three operations are supported:
  - blank_bible()          → initial scaffold for episode 1
  - merge_bible()          → merge new episode events into an existing bible
  - extract_episode_events() → LLM call to derive events from a completed script
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Schema ────────────────────────────────────────────────────────────────────

BLANK_BIBLE: dict[str, Any] = {
    "character_states": {},      # {name: {status, last_seen, notes}}
    "plot_threads": [],          # [{id, description, status: open|resolved, introduced_ep, resolved_ep}]
    "world_building": [],        # [string — established rules / facts]
    "previous_episodes": [],     # [{episode_number, summary, key_events}]
}


def blank_bible() -> dict[str, Any]:
    """Return a fresh story bible scaffold for a new serialised project."""
    import copy
    return copy.deepcopy(BLANK_BIBLE)


def merge_bible(existing: dict[str, Any] | None, new_events: dict[str, Any]) -> dict[str, Any]:
    """
    Merge *new_events* (extracted from the latest episode) into *existing*.

    *new_events* schema expected from the LLM:
    {
      "character_states": {name: {status, last_seen, notes}},
      "resolved_thread_ids": [int, ...],
      "new_threads": [{description, introduced_ep}],
      "new_world_building": [string, ...],
      "episode_summary": {episode_number, summary, key_events}
    }
    """
    bible = existing if existing is not None else blank_bible()

    # Update character states (merge, don't replace)
    for name, state in new_events.get("character_states", {}).items():
        bible["character_states"][name] = state

    # Mark resolved threads
    resolved_ids = set(new_events.get("resolved_thread_ids", []))
    for thread in bible["plot_threads"]:
        if thread.get("id") in resolved_ids:
            thread["status"] = "resolved"
            thread["resolved_ep"] = new_events.get("episode_summary", {}).get("episode_number")

    # Append new plot threads
    next_id = max((t.get("id", 0) for t in bible["plot_threads"]), default=0) + 1
    for thread in new_events.get("new_threads", []):
        bible["plot_threads"].append({
            "id": next_id,
            "description": thread.get("description", ""),
            "status": "open",
            "introduced_ep": thread.get("introduced_ep"),
            "resolved_ep": None,
        })
        next_id += 1

    # Extend world-building
    existing_wb = set(bible["world_building"])
    for rule in new_events.get("new_world_building", []):
        if rule not in existing_wb:
            bible["world_building"].append(rule)
            existing_wb.add(rule)

    # Append episode log entry
    if ep_summary := new_events.get("episode_summary"):
        bible["previous_episodes"].append(ep_summary)

    return bible


# ── LLM extraction ────────────────────────────────────────────────────────────

EXTRACT_SYSTEM = """\
You are a story bible editor for a serialised YouTube series.
Given the completed script for one episode, extract the story events needed to
update the continuity bible.

Respond ONLY with a valid JSON object:
{
  "character_states": {
    "<name>": {"status": "alive|dead|missing|unknown", "last_seen": "<location>", "notes": "<arc note>"}
  },
  "resolved_thread_ids": [<int>, ...],
  "new_threads": [{"description": "<string>", "introduced_ep": <int>}],
  "new_world_building": ["<rule or fact established in this episode>"],
  "episode_summary": {
    "episode_number": <int>,
    "summary": "<2-3 sentence synopsis>",
    "key_events": ["<event 1>", "<event 2>"]
  }
}

resolved_thread_ids: IDs from the existing bible's plot_threads that were resolved this episode.
If nothing new applies for a field, use an empty list / object.
No markdown, no explanation outside the JSON.
"""


async def extract_episode_events(
    task_id: str,
    full_script: dict,
    existing_bible: dict[str, Any] | None,
    episode_number: int,
    db=None,
    workspace_id=None,
) -> dict[str, Any] | None:
    """Call the LLM to extract story events from a completed episode script."""
    from app.services.llm_client import llm_chat, resolve_ai_config

    config = await resolve_ai_config(workspace_id, "story_bible", db) if db and workspace_id else None

    open_threads = [t for t in (existing_bible or {}).get("plot_threads", []) if t.get("status") == "open"]
    prompt = f"""\
Episode number: {episode_number}

Existing open plot threads (use these IDs in resolved_thread_ids if closed):
{json.dumps(open_threads, indent=2) if open_threads else "None"}

Full script:
{json.dumps(full_script, indent=2)}

Extract the story events now.
"""

    raw = llm_chat(system=EXTRACT_SYSTEM, user=prompt, max_tokens=2048, config=config)
    if raw is None:
        logger.warning("LLM unavailable — skipping story bible extraction for task %s", task_id)
        return None
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(raw)
    except Exception as exc:
        logger.error("Story bible extraction failed for task %s: %s", task_id, exc)
        return None
