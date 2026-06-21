# Kargov — Kurage Argo Video

`kargov` is a local-first demo/manual video generation product. It combines Kurage's browser-agent recording workflow with Argo-inspired scene alignment, subtitle overlays, transitions, and horizontal/vertical export ideas.

This repository is the product folder itself. Local data can live here during development, but Git only tracks the reusable logic and system code.

## Structure

```text
kargov/
  app/         reusable Python package and pipeline logic
  runs/        generated recordings, short edits, narration, and final videos, ignored by Git
  assets/      local fonts or private media assets, ignored by Git
  .venv/       local Python environment, ignored by Git
```

## Pipeline

```text
record
  Chrome remote debugging
  -> browser-use agent controls the page
  -> CDP Page.startScreencast captures browser frames
  -> marks.json + scenes.json draft

refine
  optional local/OAuth CLI LLM rewrites narration and captions

summarize
  trims long recordings into a short demo-ready run

narrate
  edge-tts creates per-scene narration audio

export
  ffmpeg aligns scenes to narration, burns captions, exports 16:9 and 9:16
```

## Quality Rule: No Fake Demo Videos

kargov must not produce fake, rushed, or placeholder-quality demos.

For product demos, especially kvtuber live demos:

- record the real browser operation when the video claims browser operation
- click the real admin UI when the video claims an admin button was clicked
- capture the real viewer output when the video claims live viewer playback
- preserve original seminar/viewer audio during the seminar section
- use narration only before/after or around the live section, never over the seminar audio
- avoid empty sample text, fake screens, silent captures, or low-quality filler
- verify the final MP4 with ffprobe/ffmpeg and by visual review before publishing

If the real workflow is broken, fix the workflow or state the blocker. Do not replace it with a simulated or cosmetic video.

The verified kvtuber live demo procedure is documented in
[`docs/kvtuber-live-demo-success.md`](docs/kvtuber-live-demo-success.md).
Use that procedure for `dd456c7c59e34fe5`-style replacements instead of
re-discovering the Chrome, TTS, PulseAudio, and ffmpeg sequence.

## Argo Inspiration

Argo was used as a design reference, not as a fork or copied codebase. `kargov` is a Python implementation built around the existing Kurage/browser-agent recording workflow. The Argo-inspired ideas are scene marks, narration alignment, subtitle overlays, and horizontal/vertical exports.

## Install

```bash
python3 -m pip install -e .
kargov doctor
```

System dependencies:

- Google Chrome or Chromium
- ffmpeg and ffprobe
- a browser-use compatible LLM backend, for example Ollama
- optional Claude CLI for narration refinement

## Example

```bash
kargov pipeline \
  --task "Open the target page and explain the main workflow" \
  --url "https://example.com" \
  --intro "This is an automated product demo" \
  --outro "Thanks for watching" \
  --formats 16:9,9:16

# Turn a long recording into a short demo-ready run.
kargov summarize runs/run_xxxx --target-seconds 60 --max-steps 4
kargov narrate runs/run_xxxx_short
kargov export runs/run_xxxx_short --formats 16:9,9:16
```

Outputs are written to `runs/<run>/` by default. `runs/` is ignored by Git.

## Configuration

Environment variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `KARGOV_RUNS` | output directory | `./runs` |
| `KARGOV_CHROME` | Chrome binary | `/usr/bin/google-chrome` |
| `KARGOV_FFMPEG` | ffmpeg binary | `/usr/bin/ffmpeg` |
| `KARGOV_DEBUG_PORT` | Chrome remote debugging port | `9233` |
| `OLLAMA_HOST` | local Ollama endpoint | `http://127.0.0.1:11434` |
| `KARGOV_MODEL` | browser-use model name | `gemma4:12b-it-qat` |
| `KARGOV_VOICE` | edge-tts voice | `ja-JP-NanamiNeural` |
| `KARGOV_FONT` | font file for subtitles | Noto CJK path |

## Data Boundary

Do not commit:

- `runs/` outputs
- cookies or browser profiles
- generated videos/audio/screenshots
- customer URLs or credentials
- local fonts or private media assets
- `.env` files

## Relationship to Kurage

`kargov` is the reusable browser/video automation engine. Application-specific workflows can call it from private systems or from a content engine such as `kcengine`.
