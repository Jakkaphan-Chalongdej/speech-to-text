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
    uv run transcribe.py <input-file> [--output OUT.txt] [--model large-v3-turbo]
                         [--language th] [--device auto|cpu|cuda] [--force]

Files produced next to the output:
    <name>.txt               timestamped transcript ("[HH:MM:SS] text" per line)
    <name>.transcribe.json   state file used for resume (safe to delete when done)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

SAMPLE_RATE = 16000
STATE_VERSION = 1

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


# ------------------------------------------------------------- whisper -----

def load_model(model_name: str, device: str):
    from faster_whisper import WhisperModel

    def cpu():
        print(f"[transcribe] loading model '{model_name}' on CPU (int8)", flush=True)
        return WhisperModel(model_name, device="cpu", compute_type="int8"), "cpu"

    if device == "cpu":
        return cpu()

    want_cuda = device == "cuda"
    if device == "auto":
        try:
            import ctranslate2

            want_cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            want_cuda = False

    if not want_cuda:
        return cpu()

    try:
        print(f"[transcribe] loading model '{model_name}' on GPU (CUDA)", flush=True)
        model = WhisperModel(model_name, device="cuda", compute_type="float16")
        # CUDA libraries (cuBLAS/cuDNN) are only touched on first use, so run a
        # one-second warm-up to find out now whether the GPU really works.
        import numpy as np

        segs, _ = model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language="th")
        list(segs)
        return model, "cuda"
    except Exception as e:  # missing CUDA libs, driver issues, out of memory...
        print(f"[transcribe] GPU not usable ({type(e).__name__}: {e}); falling back to CPU", flush=True)
        return cpu()


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

    model, used_device = load_model(args.model, args.device)
    state["device"] = used_device
    save_state(spath, state)

    remaining = audio[int(offset * SAMPLE_RATE):]
    del audio
    segments, _info = model.transcribe(
        remaining,
        language=args.language,
        vad_filter=True,
        condition_on_previous_text=False,
        beam_size=5,
    )

    started = time.monotonic()
    last_report = 0.0
    recent: list[str] = []
    with open(output, "ab") as out:
        for seg in segments:
            start = offset + seg.start
            end = min(offset + seg.end, total)
            text = seg.text.strip()
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
    p.add_argument("--model", default="large-v3-turbo",
                   help="faster-whisper model name or path (default: large-v3-turbo; faster: medium, small)")
    p.add_argument("--language", default="th", help="spoken language code (default: th)")
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    p.add_argument("--force", action="store_true", help="discard any existing transcript and start over")
    args = p.parse_args(argv)
    return transcribe(args)


if __name__ == "__main__":
    sys.exit(main())
