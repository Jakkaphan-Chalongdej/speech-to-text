"""Unit tests for the pure helpers in transcribe.py (no model needed).

Run:  uv run --with pytest --with faster-whisper pytest tests -q
"""

import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins/thai-meeting-transcribe/skills/transcribe/scripts/transcribe.py"
)
spec = importlib.util.spec_from_file_location("transcribe", SCRIPT)
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


def test_fmt_ts():
    assert t.fmt_ts(0) == "00:00:00"
    assert t.fmt_ts(59.9) == "00:00:59"
    assert t.fmt_ts(3725) == "01:02:05"
    assert t.fmt_ts(-3) == "00:00:00"


def test_state_path_for():
    assert t.state_path_for(Path("/a/meeting.txt")) == Path("/a/meeting.transcribe.json")


def test_decide_fresh_when_no_output(tmp_path):
    action, _ = t.decide_action(tmp_path / "m.txt", None, "large-v3-turbo", False)
    assert action == "fresh"


def test_decide_conflict_when_foreign_file(tmp_path):
    out = tmp_path / "m.txt"
    out.write_text("my own notes", encoding="utf-8")
    action, msg = t.decide_action(out, None, "large-v3-turbo", False)
    assert action == "conflict"
    assert "--force" in msg


def test_decide_conflict_on_model_change(tmp_path):
    out = tmp_path / "m.txt"
    out.write_text("", encoding="utf-8")
    state = {"model": "small", "complete": False}
    action, _ = t.decide_action(out, state, "large-v3-turbo", False)
    assert action == "conflict"


def test_decide_resume_and_done(tmp_path):
    out = tmp_path / "m.txt"
    out.write_text("", encoding="utf-8")
    assert t.decide_action(out, {"model": "m", "complete": False, "done_until": 61}, "m", False)[0] == "resume"
    assert t.decide_action(out, {"model": "m", "complete": True}, "m", False)[0] == "done"


def test_force_always_fresh(tmp_path):
    out = tmp_path / "m.txt"
    out.write_text("x", encoding="utf-8")
    assert t.decide_action(out, None, "m", True)[0] == "fresh"


def test_truncate_to_committed(tmp_path):
    out = tmp_path / "m.txt"
    committed = "[00:00:01] สวัสดีครับ\n".encode("utf-8")
    out.write_bytes(committed + "[00:00:05] ครึ่ง".encode("utf-8"))
    t.truncate_to_committed(out, {"bytes": len(committed)})
    assert out.read_bytes() == committed


def test_save_and_load_state_roundtrip(tmp_path):
    p = tmp_path / "m.transcribe.json"
    t.save_state(p, {"model": "m", "note": "ภาษาไทย"})
    assert t.load_state(p) == {"model": "m", "note": "ภาษาไทย"}
    assert json.loads(p.read_text(encoding="utf-8"))["note"] == "ภาษาไทย"
    p.write_text("{broken", encoding="utf-8")
    assert t.load_state(p) is None


def test_is_repeat():
    assert not t.is_repeat("a", [])
    assert not t.is_repeat("a", ["a"])
    assert not t.is_repeat("a", ["b", "a"])
    assert t.is_repeat("a", ["a", "a"])
