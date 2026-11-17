---
name: transcribe-meeting
description: Transcribe a meeting recording (audio or video, Thai by default) to a timestamped .txt file locally with Whisper, then write Thai meeting minutes from it. Use when the user asks to ถอดเสียง, ถอดความ, สรุปประชุม/ทำรายงานการประชุมจากไฟล์เสียงหรือวิดีโอ, or to transcribe/summarize an audio or video file (mp3, m4a, wav, mp4, mov, webm, ...).
argument-hint: <path to audio/video file> [--model small|medium|large-v3-turbo]
---

# Transcribe meeting → .txt + meeting minutes

Everything runs on the user's own machine. Audio never leaves it.

The script lives next to this file: `scripts/transcribe.py` inside this skill's
base directory (shown above as "Base directory for this skill"). Below,
`SCRIPT` means that full path. Always wrap it in double quotes, because paths may contain
spaces. On Windows, use forward slashes in the path.

Talk to the user in Thai unless they write in another language.

## 1. Check the input

- Get the file path from the arguments or the conversation. If none was given, ask for it.
- Confirm the file exists. Any common audio or video format works, and no ffmpeg is needed.
- Outputs go next to the input: `<name>.txt` (transcript) and `<name>.summary.md` (minutes).
  The script also keeps `<name>.transcribe.json` as resume state.

## 2. Make sure `uv` is available (install it if needed)

`uv` runs the script and sets up Python and every library on its own. Find it in this order,
and use the first one that works as `UV` from here on:

1. `uv --version`
2. `"$HOME/.local/bin/uv" --version` (the default install location, which may not be on PATH
   yet in this session; it works on Windows Git Bash too)

If neither works, install it **for** the user. Don't send them off to do it themselves.

- First tell them in one or two lines what will happen: it installs `uv` from Astral (the makers
  of uv) using the official installer, about 30 MB, into `~/.local/bin`. It needs no admin rights
  and is used only to run the transcription. Ask for their OK.
- Once they say yes, check the OS with `uname -s` and run:
  - `Darwin` or `Linux`: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - `MINGW*`, `MSYS*` or `CYGWIN*` (Windows): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Then check that `"$HOME/.local/bin/uv" --version` works, and use that full path as `UV`
  for the rest of this session. The user doesn't need to restart anything.
- If the install fails (no internet, a company proxy, a blocked script), show the error and the
  command above so they can run it themselves.

## 3. Run the transcription in the background

The run can take a long time, often longer than the 10-minute limit on a Bash call. So
**always start it with the Bash tool's `run_in_background: true`**:

```bash
UV run "SCRIPT" "<input file>"
```

(Here `UV` is either `uv` or `"$HOME/.local/bin/uv"`, whichever step 2 found.)

Optional flags: `--model medium` or `--model small` (faster, less accurate),
`--output <path.txt>`, `--device cpu`, and `--force` (start over and discard the existing transcript).

Before you wait, tell the user what to expect:
- The first run downloads Python packages and the model (about 1.6 GB), which takes a few minutes.
- Mac, or a PC without an NVIDIA GPU: roughly 10–20 minutes per hour of audio
  with the default model. Slow laptops take longer. A PC with a working NVIDIA GPU is much faster.
- If the run gets interrupted, running the same command again resumes where it stopped.

Then wait for the background-task notification. Don't poll in a loop. If the user
asks how it is going, read the tail of the task output: progress lines look like
`[transcribe] progress  42.0%  00:25:12 / 01:00:00`.

### When the script exits

- `[transcribe] DONE output=...` means success. Continue to step 4.
- Exit code 3 (conflict) has two causes:
  - A `.txt` with that name exists that the tool didn't create. Ask the user whether
    to choose another name (`--output`) or overwrite it (`--force`). Never pick `--force` yourself.
  - The transcript was started with a different model. Ask the user whether to resume
    with the original model or start over with `--force`.
- Other errors: show the user the last lines of the output and explain them in plain words.

## 4. Write the meeting minutes

Read the transcript. Each line is `[HH:MM:SS] text`.

- **Short transcript** (under about 1,500 lines): read it all and write the minutes in one pass.
- **Long transcript**: work in parts of about 25 minutes of timestamps, roughly 500–800 lines
  each, using Read with `offset`/`limit`. For each part, write compact notes: topics,
  points raised, decisions, action items, and the timestamps where each appears. Then merge
  the notes into one document. Don't load the whole transcript into context at once.

Rules:
- Use only what the transcript says. Never invent names, numbers, decisions or deadlines.
- Whisper mis-hears names and technical terms. Fix one only when the context makes the
  intended word clear. Otherwise keep it, and mark it `(?)` if it matters.
- Leave out obvious transcription junk, such as repeated phrases or text that appears during silence.
- Add a timestamp after each key point, e.g. `(00:12:34)`, so readers can jump back to that spot in the recording.

Write `<name>.summary.md` next to the transcript using the template in
`references/summary-template.md` (this skill's directory). Leave out any section that
has nothing in it, and don't fill sections with placeholders.

## 5. Report back

Tell the user, in a few lines:
- the paths of the `.txt` and `.summary.md` files,
- the recording length, and whether it ran on GPU or CPU (`device` in the `.transcribe.json` file),
- any parts of the transcript that looked unreliable.

The `.transcribe.json` file can be deleted once the user is happy with the result.
