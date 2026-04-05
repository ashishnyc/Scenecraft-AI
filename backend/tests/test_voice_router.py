"""Tests for the voice router (SA-24)."""
from app.services.voice_router import build_routing_manifest, NARRATOR_CHARACTER


def _make_script(scenes: list[dict]) -> dict:
    return {"scenes": scenes}


def _scene(num: int, narration: str = "", dialogue: list | None = None) -> dict:
    return {
        "scene_number": num,
        "narration": narration,
        "dialogue": dialogue or [],
        "visual_direction": "x",
        "estimated_duration_seconds": 60,
    }


NARRATOR_VOICE = "voice-narrator"
ALEX_VOICE = "voice-alex"
JORDAN_VOICE = "voice-jordan"

CAST = {"Alex": ALEX_VOICE, "Jordan": JORDAN_VOICE}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_empty_script_returns_empty_manifest():
    result = build_routing_manifest({"scenes": []}, {}, NARRATOR_VOICE)
    assert result == []


def test_narration_uses_narrator_voice():
    script = _make_script([_scene(1, narration="Welcome to the show.")])
    manifest = build_routing_manifest(script, CAST, NARRATOR_VOICE)
    assert len(manifest) == 1
    assert manifest[0]["voice_profile_id"] == NARRATOR_VOICE
    assert manifest[0]["character_name"] == NARRATOR_CHARACTER
    assert manifest[0]["line_type"] == "narration"


def test_dialogue_routes_to_character_voice():
    script = _make_script([_scene(1, dialogue=[{"character": "Alex", "line": "Hello."}])])
    manifest = build_routing_manifest(script, CAST, NARRATOR_VOICE)
    assert len(manifest) == 1
    assert manifest[0]["voice_profile_id"] == ALEX_VOICE
    assert manifest[0]["character_name"] == "Alex"
    assert manifest[0]["line_type"] == "dialogue"


def test_three_characters_all_routed():
    script = _make_script([
        _scene(1,
               narration="Scene opens.",
               dialogue=[
                   {"character": "Alex", "line": "Hi."},
                   {"character": "Jordan", "line": "Hey."},
               ]),
    ])
    manifest = build_routing_manifest(script, CAST, NARRATOR_VOICE)
    assert len(manifest) == 3
    voices = {e["character_name"]: e["voice_profile_id"] for e in manifest}
    assert voices[NARRATOR_CHARACTER] == NARRATOR_VOICE
    assert voices["Alex"] == ALEX_VOICE
    assert voices["Jordan"] == JORDAN_VOICE


def test_unassigned_character_falls_back_to_narrator():
    script = _make_script([_scene(1, dialogue=[{"character": "Ghost", "line": "Boo."}])])
    manifest = build_routing_manifest(script, CAST, NARRATOR_VOICE)
    assert manifest[0]["voice_profile_id"] == NARRATOR_VOICE
    assert manifest[0]["character_name"] == "Ghost"


def test_character_with_none_voice_falls_back():
    cast = {"Alex": None}  # no voice assigned
    script = _make_script([_scene(1, dialogue=[{"character": "Alex", "line": "Hi."}])])
    manifest = build_routing_manifest(script, cast, NARRATOR_VOICE)
    assert manifest[0]["voice_profile_id"] == NARRATOR_VOICE


def test_line_indices_are_sequential():
    script = _make_script([
        _scene(1, narration="Act 1", dialogue=[{"character": "Alex", "line": "A"}]),
        _scene(2, narration="Act 2", dialogue=[{"character": "Jordan", "line": "B"}]),
    ])
    manifest = build_routing_manifest(script, CAST, NARRATOR_VOICE)
    assert [e["line_index"] for e in manifest] == list(range(len(manifest)))


def test_scene_numbers_preserved():
    script = _make_script([
        _scene(3, narration="Third scene."),
        _scene(7, narration="Seventh scene."),
    ])
    manifest = build_routing_manifest(script, {}, NARRATOR_VOICE)
    assert manifest[0]["scene_number"] == 3
    assert manifest[1]["scene_number"] == 7


def test_lookup_is_case_insensitive():
    cast = {"ALEX": ALEX_VOICE}
    script = _make_script([_scene(1, dialogue=[{"character": "alex", "line": "Hi."}])])
    manifest = build_routing_manifest(script, cast, NARRATOR_VOICE)
    assert manifest[0]["voice_profile_id"] == ALEX_VOICE


def test_empty_dialogue_line_skipped():
    script = _make_script([_scene(1, dialogue=[{"character": "Alex", "line": ""}])])
    manifest = build_routing_manifest(script, CAST, NARRATOR_VOICE)
    assert manifest == []
