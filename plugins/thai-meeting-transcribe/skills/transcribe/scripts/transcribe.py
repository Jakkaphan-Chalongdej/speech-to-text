# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "faster-whisper>=1.1.0,<2",
#   # PyAV 19 removed open(metadata_errors=...), which faster-whisper 1.2.x still passes.
#   "av>=11,<19",
# ]
# ///
"""Transcribe an audio/video file (Thai by default) to a timestamped .txt file.

Runs fully on the local machine with faster-whisper. Designed for long
meetings: output is written incrementally and an interrupted run resumes
where it stopped.

Usage:
    uv run transcribe.py <input-file> [--output OUT.txt] [--model NAME]
                         [--language th] [--device auto|cpu|cuda|mps] [--force]

Default model: Typhoon Whisper Turbo (typhoon-ai, MIT), Thai fine-tune of
whisper-large-v3-turbo, in the CTranslate2 format faster-whisper needs. On a
real Thai meeting it was far more accurate than plain large-v3-turbo at the
same speed.

Files produced next to the output:
    <name>.txt               timestamped transcript ("[HH:MM:SS] text" per line)
    <name>.transcribe.json   state file used for resume (safe to delete when done)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

SAMPLE_RATE = 16000
STATE_VERSION = 1

# Community CTranslate2 conversion of typhoon-ai/typhoon-whisper-turbo, pinned to
# an exact commit so the downloaded weights can never change underneath users.
DEFAULT_MODEL = "sub247/typhoon-whisper-turbo-ct2"
DEFAULT_MODEL_REVISION = "3322777153e1f149aa2c1988db6b460c1621753c"

# Exit codes
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CONFLICT = 3


# ---------------------------------------------------------------- helpers ---

def fmt_ts(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def state_path_for(output: Path) -> Path:
    return output.with_name(output.stem + ".transcribe.json")


def load_state(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def decide_action(output: Path, state: dict | None, model: str, force: bool) -> tuple[str, str]:
    """Decide what to do given existing files.

    Returns (action, message) where action is one of:
      "fresh"    start a new transcript
      "resume"   continue an unfinished transcript
      "done"     transcript already complete, nothing to do
      "conflict" refuse (message explains why)
    """
    if force:
        return "fresh", "starting fresh (--force)"
    if not output.exists():
        return "fresh", "starting new transcript"
    if state is None:
        return (
            "conflict",
            f"{output} already exists and was not created by this tool. "
            "Use --output to pick another file name, or --force to overwrite it.",
        )
    if state.get("model") != model:
        return (
            "conflict",
            f"{output} was started with model '{state.get('model')}', not '{model}'. "
            "Resuming would mix two models. Use --force to start over with the new model.",
        )
    if state.get("complete"):
        return "done", f"{output} is already complete"
    return "resume", f"resuming from {fmt_ts(state.get('done_until', 0.0))}"


def truncate_to_committed(output: Path, state: dict) -> None:
    """Drop any text written after the last committed segment (e.g. after a crash)."""
    committed = int(state.get("bytes", 0))
    with open(output, "r+b") as f:
        f.truncate(committed)


def is_repeat(text: str, recent: list[str]) -> bool:
    """True if this text is the same as each of the last two segments (a loop)."""
    return len(recent) >= 2 and all(t == text for t in recent[-2:])


# Scripts allowed in a Thai transcript: Thai, printable ASCII (English terms,
# digits, punctuation) and general punctuation (curly quotes, dashes, ellipsis).
# Anything else (Hangul, CJK, Cyrillic, Greek, Arabic, ...) is a Whisper
# hallucination on unclear audio.
_NOT_THAI_OR_ASCII = re.compile(r"[^฀-๿\x20-\x7E -⁯]+")
_HAS_CONTENT = re.compile(r"[฀-๿0-9A-Za-z]")
# A run of 2-20 non-space, non-digit characters repeated 3+ times with no
# spaces, e.g. "เกราะเกราะเกราะ". Digits are excluded so "1000000" survives.
_GLUED_LOOP = re.compile(r"([^\s\d]{2,20}?)\1{2,}")


def strip_foreign(text: str, language: str) -> str:
    """Remove characters from scripts that cannot appear in this language's transcript."""
    if language != "th":
        return text
    return " ".join(_NOT_THAI_OR_ASCII.sub(" ", text).split())


def collapse_repeats(text: str, min_repeats: int = 3) -> str:
    """Collapse a word or phrase repeated min_repeats+ times in a row into one copy."""
    words = text.split()
    changed = True
    while changed:
        changed = False
        for n in range(1, 9):
            out: list[str] = []
            i = 0
            while i < len(words):
                gram = words[i:i + n]
                if len(gram) == n:
                    k = 1
                    while words[i + k * n:i + (k + 1) * n] == gram:
                        k += 1
                    if k >= min_repeats:
                        out.extend(gram)
                        i += k * n
                        changed = True
                        continue
                out.append(words[i])
                i += 1
            words = out
    return _GLUED_LOOP.sub(r"\1", " ".join(words))


def merge_spans(spans, max_len: float, max_gap: float = 1.0) -> list[list[float]]:
    """Merge speech spans (start, end) in seconds into windows of at most max_len.

    Neighbouring spans are joined when the gap is short and the result still fits.
    """
    out: list[list[float]] = []
    for s, e in spans:
        if out and s - out[-1][1] <= max_gap and e - out[-1][0] <= max_len:
            out[-1][1] = e
        else:
            out.append([s, e])
    return out


def speech_windows(audio, max_len: float) -> list[float]:
    """Find speech with VAD and return flat [start, end, start, end, ...] in seconds.

    Each window is decoded on its own. Short windows matter for Thai: 30 s of fast
    Thai speech can exceed Whisper's per-window token limit, and models fine-tuned
    without timestamps then silently drop the rest of that window.
    """
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    opts = VadOptions(max_speech_duration_s=max_len, min_silence_duration_ms=500)
    spans = [(c["start"] / SAMPLE_RATE, c["end"] / SAMPLE_RATE)
             for c in get_speech_timestamps(audio, opts)]
    return [x for w in merge_spans(spans, max_len) for x in w]


def clean_text(text: str, language: str) -> str:
    """Filter one segment; returns "" when nothing meaningful is left."""
    text = collapse_repeats(strip_foreign(text, language)).strip()
    return text if _HAS_CONTENT.search(text) else ""


# ------------------------------------------------------------- whisper -----

def default_threads() -> int:
    """CPU threads to use.

    Apple Silicon: only the performance cores. Measured on an M5 (4P + 6E), 10
    threads ran slower than 4 because the efficiency cores hold the others back.
    Elsewhere: roughly the physical cores (logical count / 2), between 4 and 8.
    """
    if sys.platform == "darwin":
        try:
            import subprocess

            out = subprocess.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
            if out.isdigit() and int(out) > 0:
                return int(out)
        except Exception:
            pass
    logical = os.cpu_count() or 4
    return max(min(4, logical), min(logical // 2, 8))


def is_apple_silicon() -> bool:
    import platform

    return sys.platform == "darwin" and platform.machine() == "arm64"


def candidate_devices(device: str) -> list[str]:
    """Devices to try in order. CPU is always the last resort.

    auto: NVIDIA GPU if present, Apple GPU (MPS) on Apple Silicon, then CPU.
    MPS measured ~1.4x faster than CPU on an M5 with the same output quality.
    """
    if device != "auto":
        return [device] if device == "cpu" else [device, "cpu"]
    devices = []
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            devices.append("cuda")
    except Exception:
        pass
    if is_apple_silicon():
        devices.append("mps")
    return devices + ["cpu"]


def model_revision(model_name: str, revision: str | None) -> str | None:
    if revision:
        return revision
    return DEFAULT_MODEL_REVISION if model_name == DEFAULT_MODEL else None


def load_model(model_name: str, device: str, threads: int, revision: str | None = None):
    from faster_whisper import WhisperModel
    import numpy as np

    rev = model_revision(model_name, revision)
    for dev in candidate_devices(device):
        compute = "int8" if dev == "cpu" else "auto"
        print(f"[transcribe] loading model '{model_name}' on {dev.upper()} "
              f"({compute}{f', {threads} threads' if dev == 'cpu' else ''})", flush=True)
        try:
            model = WhisperModel(model_name, device=dev, compute_type=compute,
                                 cpu_threads=threads, revision=rev)
            if dev != "cpu":
                # GPU libraries (cuBLAS/cuDNN, Metal) are only touched on first use, so run
                # a one-second warm-up to find out now whether the device really works.
                segs, _ = model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language="th")
                list(segs)
            return model, dev
        except Exception as e:  # missing CUDA libs, unsupported device, out of memory...
            if dev == "cpu":
                raise
            print(f"[transcribe] {dev.upper()} not usable ({type(e).__name__}: {e}); trying next device", flush=True)
    raise RuntimeError("no usable device")


def transcribe(args: argparse.Namespace) -> int:
    src = Path(args.input).expanduser().resolve()
    if not src.is_file():
        print(f"[transcribe] input file not found: {src}", file=sys.stderr)
        return EXIT_USAGE

    output = Path(args.output).expanduser().resolve() if args.output else src.with_suffix(".txt")
    if output == src:
        print("[transcribe] output path would overwrite the input file", file=sys.stderr)
        return EXIT_USAGE
    spath = state_path_for(output)
    state = load_state(spath)

    action, msg = decide_action(output, state, args.model, args.force)
    print(f"[transcribe] {msg}", flush=True)
    if action == "conflict":
        print(f"[transcribe] ERROR: {msg}", file=sys.stderr)
        return EXIT_CONFLICT
    if action == "done":
        print(f"[transcribe] DONE output={output}", flush=True)
        return EXIT_OK

    if action == "fresh":
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"")
        state = {
            "version": STATE_VERSION,
            "input": str(src),
            "model": args.model,
            "language": args.language,
            "done_until": 0.0,
            "bytes": 0,
            "complete": False,
        }
        save_state(spath, state)
    else:
        truncate_to_committed(output, state)

    from faster_whisper import decode_audio

    print(f"[transcribe] reading audio from {src.name}", flush=True)
    audio = decode_audio(str(src), sampling_rate=SAMPLE_RATE)
    total = len(audio) / SAMPLE_RATE
    offset = float(state["done_until"])
    print(f"[transcribe] duration {fmt_ts(total)}; starting at {fmt_ts(offset)}", flush=True)

    model, used_device = load_model(args.model, args.device, args.threads or default_threads(),
                                    args.revision)
    state["device"] = used_device
    save_state(spath, state)

    remaining = audio[int(offset * SAMPLE_RATE):]
    del audio
    windows = speech_windows(remaining, args.window)
    print(f"[transcribe] {len(windows) // 2} speech windows (max {args.window:g}s each)", flush=True)
    if windows:
        segments, _info = model.transcribe(
            remaining,
            language=args.language,
            clip_timestamps=windows,
            condition_on_previous_text=False,
            beam_size=5,
        )
    else:
        segments = []

    started = time.monotonic()
    last_report = 0.0
    recent: list[str] = []
    with open(output, "ab") as out:
        for seg in segments:
            start = offset + seg.start
            end = min(offset + seg.end, total)
            text = seg.text.strip()
            if not args.no_filter:
                text = clean_text(text, args.language)
            if text and not is_repeat(text, recent):
                out.write(f"[{fmt_ts(start)}] {text}\n".encode("utf-8"))
                out.flush()
            recent.append(text)
            recent[:] = recent[-2:]

            state["done_until"] = end
            state["bytes"] = out.tell()
            save_state(spath, state)

            now = time.monotonic()
            if now - last_report >= 5 or end >= total:
                last_report = now
                pct = 100.0 * end / total if total else 100.0
                print(
                    f"[transcribe] progress {pct:5.1f}%  {fmt_ts(end)} / {fmt_ts(total)}"
                    f"  (elapsed {fmt_ts(now - started)})",
                    flush=True,
                )

    state["done_until"] = total
    state["complete"] = True
    save_state(spath, state)
    print(f"[transcribe] DONE output={output}", flush=True)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    # Thai text must not crash on Windows consoles using a legacy code page.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    p = argparse.ArgumentParser(description="Transcribe audio/video to a timestamped .txt (local, faster-whisper).")
    p.add_argument("input", help="audio or video file")
    p.add_argument("--output", help="output .txt path (default: next to the input, same name)")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"faster-whisper model: Hugging Face repo id, built-in name (e.g. large-v3-turbo) "
                        f"or local folder (default: {DEFAULT_MODEL}, Thai)")
    p.add_argument("--revision", help="model repo commit/branch (default model is pinned)")
    p.add_argument("--language", default="th", help="spoken language code (default: th)")
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"],
                   help="auto = NVIDIA GPU if it works, else CPU; mps = Apple GPU (experimental)")
    p.add_argument("--threads", type=int, default=0,
                   help="CPU threads (default: all cores on this machine)")
    p.add_argument("--window", type=float, default=15.0,
                   help="max seconds of speech decoded at once (default: 15; Whisper's limit is 30)")
    p.add_argument("--no-filter", action="store_true",
                   help="keep raw Whisper text (no repeat/foreign-script cleanup)")
    p.add_argument("--force", action="store_true", help="discard any existing transcript and start over")
    args = p.parse_args(argv)
    return transcribe(args)


if __name__ == "__main__":
    sys.exit(main())
