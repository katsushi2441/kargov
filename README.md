# Kurage Argo Video (kargov)

Browser-agent video automation pipeline for recording web app demos, tutorials,
and narrated operation videos.

`kargov` combines browser automation, Chrome DevTools Protocol screencast
capture, scene manifests, TTS narration, subtitle overlays, and 16:9 / 9:16
exports into a local-first video generation workflow.

This repository contains only reusable logic and system code. Generated runs,
recordings, screenshots, customer data, cookies, API keys, and production
outputs must stay outside the repository.

## Pipeline

```text
record
  Chrome remote debugging
  -> browser-use agent controls the page
  -> CDP Page.startScreencast captures browser frames
  -> marks.json + scenes.json draft

refine
  optional local/OAuth CLI LLM rewrites narration and captions

narrate
  edge-tts creates per-scene narration audio

export
  ffmpeg aligns scenes to narration, burns captions, exports 16:9 and 9:16
```

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
  --task "Open the demo page and explain the main workflow" \
  --url "https://example.com" \
  --intro "This is an automated product demo" \
  --outro "Thanks for watching" \
  --formats 16:9,9:16
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
- `.env` files

## Relationship to Kurage

`kargov` is the reusable browser/video automation engine. Application-specific
content workflows can call it from private repositories or from a content engine
such as `kcengine`.
