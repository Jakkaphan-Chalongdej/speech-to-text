# Thai Meeting Transcribe — Claude Code Plugin (Design)

Date: 2026-11-17
Status: implemented (v0.1.0); see "Decisions made during build" at the end

## Intent / why

The author wants to share a Claude Code plugin with friends so they can turn
recordings of **Thai-language meetings** (audio or video files) into text and
then into meeting minutes. Claude cannot listen to audio itself, so the plugin
supplies a speech-to-text step and lets Claude do the writing afterwards.

Who: friends who already use **Claude Code**, on **macOS and Windows**.

## Goals

1. One command turns an audio/video file into:
   - a plain **`.txt` transcript** (for reuse elsewhere), and
   - a **meeting-summary document** written by Claude from that transcript.
2. Works the same on macOS and Windows with minimal setup.
3. Handles **long meetings** (2–3 hours) reliably.
4. Meeting audio **never leaves the user's machine** for transcription.

## Non-goals

- Speaker identification ("who said what") — not needed.
- Real-time / live transcription.
- Languages other than Thai as a design target (Whisper will still handle
  others, but nothing is tuned for them).
- A GUI. This lives inside Claude Code.

## Anti-goals (failure even if it "works")

- Requires friends to manage API keys or pay per use.
- Setup that differs a lot between Mac and Windows, or that needs ffmpeg /
  manual binary downloads.
- A long meeting silently loses its whole transcript because the run was cut
  off or interrupted.
- The transcript contains repeated loops or invented sentences during silence
  that then pollute the summary.

## Constraints

- Claude Code's Bash tool times out after at most 10 minutes; transcription of a
  long meeting on CPU can take 30–60 minutes.
- Thai text is token-heavy: about 40k–60k tokens per hour of meeting. A 3-hour
  transcript approaches Claude's context limit.
- Friends' machines vary: Apple Silicon Macs (CPU only for this stack),
  Windows with or without an NVIDIA GPU.

## Approaches considered

| Approach | Trade-offs | Decision |
|---|---|---|
| **A. Local faster-whisper, run via `uv`** | Free, private, same on Mac & Windows, no ffmpeg needed (PyAV decodes media). CPU-only on Mac → ~10–20 min per hour of audio. First run downloads ~1.6 GB model. | **Chosen** |
| B. Cloud API (OpenAI / ElevenLabs) | Fastest, slightly better Thai, but each friend needs an API key, pays ~10–15 THB/hour, meeting content leaves the machine, files must be split to ~25 MB. | Rejected — privacy & key/cost burden |
| C. Support both, selectable | Most flexible, double the build & maintenance. | Rejected — not needed now |
| (whisper.cpp) | Fast on Mac via Homebrew, awkward to install on Windows. | Rejected — cross-platform |
| (mlx-whisper) | Very fast on Mac, does not run on Windows. | Rejected — cross-platform |

The author chose **A**.

## Design

### Distribution

- The plugin lives in a Git repository (e.g. GitHub) that also acts as a
  Claude Code **plugin marketplace** (`.claude-plugin/marketplace.json`).
- Friends install with `/plugin marketplace add <repo>` then
  `/plugin install <plugin-name>`.
- One prerequisite per machine: install **`uv`** (one documented command for
  macOS, one for Windows PowerShell). `uv` provisions Python and dependencies
  automatically.

### Components

1. **Transcription script** (Python, single file, PEP 723 inline dependencies,
   run with `uv run`), referenced via `${CLAUDE_PLUGIN_ROOT}`.
   - Uses `faster-whisper`, default model `large-v3-turbo`, language forced to
     `th`.
   - Device auto-detect: CUDA if available, else CPU (int8).
   - Enables built-in VAD filter and disables conditioning on previous text, to
     prevent silence hallucinations and repetition loops.
   - Writes segments to the output `.txt` **incrementally** as they are decoded,
     each line prefixed with a timestamp (e.g. `[00:12:34]`).
   - **Resumable**: on re-run, detects how far the existing output got and
     continues from there instead of starting over.
   - Prints progress (percent / elapsed position) so the user and Claude can see
     it is moving.
   - `--model` option to swap in another model later (e.g. a Thai fine-tune).
2. **Slash command / skill** (e.g. `/transcribe <file>`), the user-facing entry:
   - Checks `uv` is installed; if not, tells the user the exact install command
     for their OS.
   - Starts the script **in the background** so the 10-minute tool timeout does
     not apply, and waits for the completion notification.
   - When done, produces the meeting summary (below).
3. **Summary step** (done by Claude, guided by instructions in the skill):
   - Short transcripts: summarize in one pass.
   - Long transcripts: summarize in time-window chunks (~20–30 min each), then
     merge into one document.
   - Claude should fix obvious mis-transcriptions of names/terms when context
     makes them clear, but never invent content.
   - Summary sections (Thai): topic/meeting info, key discussion points,
     decisions (มติ), action items (who/what/when when stated), open questions.

### Outputs

Written next to the source file (my call — keeps results with the recording):

- `<name>.txt` — timestamped transcript.
- `<name>.summary.md` — meeting minutes in Thai.

## Calls I made (correct me if wrong)

- Default model `large-v3-turbo` (good speed/accuracy balance); Thai fine-tune
  is a later option, not part of v1.
- Timestamps in the `.txt` file (cheap, helps jump back into the recording).
- Summary format is Markdown; can be turned into Word later if wanted.
- Outputs saved beside the input file.

## Left to the builder

- Exact plugin/command names and repo layout within Claude Code's plugin format.
- How resume detection is implemented.
- Progress output format.
- README wording and install instructions per OS.
- How to test (e.g. a short Thai sample clip).

## Decisions made during build

- **uv install**: the skill installs `uv` itself on first use, after asking the user, via
  Astral's official installer. It then calls it as `$HOME/.local/bin/uv`, so no restart is
  needed. A hook that installs silently on every session start was rejected for trust reasons.
  Claude Code's auto mode may block `curl | sh`, so the skill falls back to showing the command.
- **GPU**: CUDA is used only if it actually works (checked with a 1-second warm-up). Otherwise
  the script falls back to CPU. CUDA libraries are not bundled.
- **Existing output file**: if a `.txt` has no state file, the script refuses (exit 3). If the
  model differs from the one recorded, it refuses (exit 3). If the transcript is already
  complete, it skips. `--force` starts over. State lives in `<name>.transcribe.json` and
  records the byte length committed, for crash-safe resume.
- **Windows**: best effort; not yet tested on a real machine.
- **PyAV pinned `<19`**: PyAV 19 removed `open(metadata_errors=...)`, which faster-whisper 1.2.x
  still passes.

## v0.2.0 changes (2026-11-18), from testing on a real 36-minute Thai meeting

- **Default model is Typhoon Whisper Turbo** (`sub247/typhoon-whisper-turbo-ct2`, pinned
  commit), a CTranslate2 conversion of `typhoon-ai/typhoon-whisper-turbo` (MIT). It ran at the
  same speed as `large-v3-turbo` with far better Thai.
- **15-second speech windows** come from VAD and are passed as `clip_timestamps`. Thai
  fine-tunes don't emit timestamps, so with 30-second windows they hit the per-window token
  limit and dropped almost half the text (1,739 → 3,296 Thai chars on the same clip).
- **Output filters**: Hangul, CJK, Cyrillic and other scripts are stripped from Thai output,
  and a word or phrase repeated 3+ times in a row collapses to one copy. Lines with no
  content left are dropped. `--no-filter` turns this off.
- **Devices**: auto mode tries CUDA, then MPS on Apple Silicon (about 1.4× faster than CPU on
  an M5), then CPU. CPU threads default to the performance cores: on an M5, 10 threads were
  slower than 4.
