"""LLM-powered consistency checker (Script Pipeline — Stage 3).

Reviews the full assembled script for plot holes, character inconsistencies,
tone deviations, and pacing issues.  Blockers cause targeted scene re-generation
via the scene expander; warnings are recorded but do not block progression.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, model_validator

from app.core.config import get_settings
from app.services.scene_expander import expand_scenes

logger = logging.getLogger(__name__)

MAX_RETRIES = 1  # one re-generation pass for blocker scenes


# ── Output schema ─────────────────────────────────────────────────────────────

class ConsistencyFlag(BaseModel):
    scene_number: int
    issue_type: Literal["plot_hole", "character_inconsistency", "tone_deviation", "pacing_issue"]
    description: str
    severity: Literal["warning", "blocker"]


class ConsistencyReport(BaseModel):
    flags: list[ConsistencyFlag]

    @model_validator(mode="after")
    def compute_has_blockers(self) -> "ConsistencyReport":
        # expose as a computed attribute for callers
        object.__setattr__(self, "has_blockers", any(f.severity == "blocker" for f in self.flags))
        return self

    @property
    def blocker_scene_numbers(self) -> list[int]:
        return [f.scene_number for f in self.flags if f.severity == "blocker"]


# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a senior script editor reviewing a YouTube video screenplay.
Analyse the full script for internal consistency issues.

Respond ONLY with a valid JSON object:
{
  "flags": [
    {
      "scene_number": <int>,
      "issue_type": "plot_hole" | "character_inconsistency" | "tone_deviation" | "pacing_issue",
      "description": "<concise explanation of the issue>",
      "severity": "warning" | "blocker"
    }
  ]
}

Severity guide:
- blocker: the issue would confuse the audience or break the story (missing information,
           contradictions, characters appearing before they are introduced)
- warning: minor inconsistency or stylistic suggestion that can be left as-is

If no issues are found, return {"flags": []}.
No markdown, no explanation outside the JSON.
"""


def _build_check_prompt(full_script: dict, style_guide: dict) -> str:
    style_text = json.dumps(style_guide, indent=2) if style_guide else "Not specified"
    script_text = json.dumps(full_script, indent=2)
    return f"""\
Style guide:
{style_text}

Full script to review:
{script_text}

Identify all consistency issues now.
"""


def _parse_report(raw: str) -> ConsistencyReport:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    data = json.loads(text)
    return ConsistencyReport(**data)


# ── Main entry point ──────────────────────────────────────────────────────────

async def check_consistency(
    task_id: str,
    full_script: dict,
    style_guide: dict,
    cast_profiles: dict[str, str | None],
    outline: dict,
    *,
    _retry: int = 0,
) -> dict[str, Any] | None:
    """
    Run a consistency check over *full_script*.

    If blockers are found, re-generates only the affected scenes (once) via the
    scene expander, then re-runs the check on the updated script.

    Returns the final ``ConsistencyReport`` dict (flags may be empty), or
    ``None`` on LLM failure.
    """
    from app.services.llm_client import llm_chat

    prompt = _build_check_prompt(full_script, style_guide)
    raw = llm_chat(system=SYSTEM_PROMPT, user=prompt, max_tokens=2048)
    if raw is None:
        logger.warning("LLM unavailable — skipping consistency check for task %s", task_id)
        return None

    try:
        report = _parse_report(raw)
    except (json.JSONDecodeError, Exception) as exc:
        logger.error("Failed to parse consistency report (task %s): %s\nRaw: %s", task_id, exc, raw[:500])
        return None

    logger.info(
        "Consistency check for task %s: %d flags (%d blockers)",
        task_id, len(report.flags), len(report.blocker_scene_numbers),
    )

    # If blockers remain and we haven't retried yet, re-generate the bad scenes
    if report.has_blockers and _retry < MAX_RETRIES:  # type: ignore[attr-defined]
        blocker_nums = set(report.blocker_scene_numbers)
        logger.info("Re-generating %d blocker scene(s) for task %s", len(blocker_nums), task_id)

        # Rebuild outline containing only blocker scenes so the expander re-runs them
        blocker_outline = {
            "acts": [
                {
                    **act,
                    "scenes": [s for s in act["scenes"] if s["scene_number"] in blocker_nums],
                }
                for act in outline.get("acts", [])
            ]
        }
        blocker_outline["acts"] = [a for a in blocker_outline["acts"] if a["scenes"]]

        regenerated = await expand_scenes(
            task_id=task_id,
            outline=blocker_outline,
            cast_profiles=cast_profiles,
        )
        if regenerated:
            # Merge regenerated scenes back into the full script
            regen_by_num = {s["scene_number"]: s for s in regenerated["scenes"]}
            updated_scenes = [
                regen_by_num.get(s["scene_number"], s)
                for s in full_script.get("scenes", [])
            ]
            full_script = {**full_script, "scenes": updated_scenes}

            # One more consistency pass on the updated script
            return await check_consistency(
                task_id, full_script, style_guide, cast_profiles, outline, _retry=_retry + 1
            )

    return report.model_dump()
