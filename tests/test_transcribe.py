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


def test_collapse_repeats_words():
    text = "อันนี้มันไม่เก็บ " + "ไม่เก็บ " * 30 + "จบ"
    assert t.collapse_repeats(text) == "อันนี้มันไม่เก็บ ไม่เก็บ จบ"


def test_collapse_repeats_phrases():
    text = "อ.เจมส์ " + "ต้องใช้อย่างนั้น " * 20
    assert t.collapse_repeats(text) == "อ.เจมส์ ต้องใช้อย่างนั้น"


def test_collapse_repeats_multiword_phrase():
    text = "ก่อน " + "ไม่ได้ ครับ " * 5 + "หลัง"
    assert t.collapse_repeats(text) == "ก่อน ไม่ได้ ครับ หลัง"


def test_collapse_repeats_glued_thai():
    assert t.collapse_repeats("มีเกราะเกราะเกราะ") == "มีเกราะ"


def test_collapse_repeats_keeps_normal_doubles():
    # Two repeats are normal speech; only 3+ is treated as a loop.
    assert t.collapse_repeats("ใช่ ใช่ ได้ค่ะ") == "ใช่ ใช่ ได้ค่ะ"
    assert t.collapse_repeats("เย็นๆ ค่ะ 55") == "เย็นๆ ค่ะ 55"


def test_strip_foreign_removes_other_scripts_for_thai():
    assert t.strip_foreign("แยกเกิ่งมา으로 ให้เรา", "th") == "แยกเกิ่งมา ให้เรา"
    assert t.strip_foreign("ทำไมก็จะได้ใช้五60 ตอน", "th") == "ทำไมก็จะได้ใช้ 60 ตอน"
    assert t.strip_foreign("แบบ musste Ведь", "th") == "แบบ musste"


def test_strip_foreign_keeps_thai_and_english_terms():
    s = "ปุ่ม Export PDF ให้ SuperAdmin 5 ระดับ (ประมาณ 69%) “ok” – ใช่ไหม?"
    assert t.strip_foreign(s, "th") == s


def test_strip_foreign_only_applies_to_thai():
    assert t.strip_foreign("Ведь", "ru") == "Ведь"


def test_clean_text_drops_junk_only_lines():
    assert t.clean_text("넥 ...", "th") == ""
    assert t.clean_text("...", "th") == ""
    assert t.clean_text("ได้ค่ะ", "th") == "ได้ค่ะ"


def test_merge_spans_joins_close_spans_up_to_max_len():
    spans = [(0.0, 4.0), (4.5, 9.0), (9.5, 14.0), (14.2, 20.0)]
    assert t.merge_spans(spans, max_len=15) == [[0.0, 14.0], [14.2, 20.0]]


def test_merge_spans_keeps_long_gaps_apart():
    assert t.merge_spans([(0, 3), (10, 12)], max_len=15) == [[0, 3], [10, 12]]


def test_merge_spans_empty():
    assert t.merge_spans([], max_len=15) == []


def test_candidate_devices_always_end_with_cpu():
    assert t.candidate_devices("cpu") == ["cpu"]
    assert t.candidate_devices("mps") == ["mps", "cpu"]
    assert t.candidate_devices("cuda") == ["cuda", "cpu"]
    assert t.candidate_devices("auto")[-1] == "cpu"


def test_auto_tries_mps_only_on_apple_silicon(monkeypatch):
    monkeypatch.setattr(t, "is_apple_silicon", lambda: True)
    assert t.candidate_devices("auto")[-2:] == ["mps", "cpu"]
    monkeypatch.setattr(t, "is_apple_silicon", lambda: False)
    assert "mps" not in t.candidate_devices("auto")


def test_default_model_is_pinned():
    assert t.model_revision(t.DEFAULT_MODEL, None) == t.DEFAULT_MODEL_REVISION
    assert t.model_revision("large-v3-turbo", None) is None
    assert t.model_revision(t.DEFAULT_MODEL, "main") == "main"


def test_default_threads_positive():
    assert t.default_threads() >= 1


def test_is_repeat():
    assert not t.is_repeat("a", [])
    assert not t.is_repeat("a", ["a"])
    assert not t.is_repeat("a", ["b", "a"])
    assert t.is_repeat("a", ["a", "a"])
