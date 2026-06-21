# kvtuber Live Demo Success Procedure

This document records the working procedure for replacing the public Kurage
video `dd456c7c59e34fe5` with a real kvtuber live demo recording.

## Successful Reference

- Public video: `https://kurage.exbridge.jp/kuragev.php?id=dd456c7c59e34fe5`
- Original successful run: `runs/kvtuber_live_demo_20260621_093104`
- Fixed successful rerun: `runs/kvtuber_live_demo_20260621_113808_waitaudio`
- Final replacement: `/home/kojima/work/kurage/storage/jobs/dd456c7c59e34fe5/output.mp4`

## Required Conditions

1. kvtuber must be started in a persistent session, not a short-lived command.
2. kvtuber must use a Python that has `edge_tts` installed.
3. Chrome must run on the visible VNC/Xvfb display `:99`.
4. Chrome must send audio to the PulseAudio null sink `kurage_live`.
5. Recording must not start immediately after clicking `配信開始`.
6. Wait for real Pulse audio from `kurage_live.monitor`; `-91 dB` means failure.

## kvtuber Server

Start the dev server in a long-lived session:

```bash
cd /home/kojima/work/kvtuber
export KURAGE_ADMIN_TOKEN=kurage-admin
export KURAGE_TTS_PYTHON=/home/kojima/work/kargov/.venv/bin/python
export KVTUBER_PORT=18308
npm run dev -- --host 0.0.0.0 --port 18308
```

Verify TTS before recording:

```bash
curl -sS -X POST 'http://127.0.0.1:18308/kurage-tts/v1/audio/speech' \
  -H 'Content-Type: application/json' \
  -d '{"input":"これは音声テストです。","voice":"ja-JP-NanamiNeural"}' \
  -o /tmp/kvt_tts_test.mp3

/usr/bin/ffmpeg -hide_banner -i /tmp/kvt_tts_test.mp3 \
  -af volumedetect -f null -
```

Expected result is real audio around `mean_volume: -17 dB`. If the response is
JSON with `ModuleNotFoundError: No module named 'edge_tts'`, the server was
started with the wrong Python.

## Chrome / VNC

Chrome must stay attached to a persistent command session. In this environment
`tmux` and `screen` are not installed, so use the Codex long-running command
session equivalent.

```bash
DISPLAY=:99 PULSE_SINK=kurage_live google-chrome \
  --remote-debugging-port=9223 \
  --remote-debugging-address=127.0.0.1 \
  --remote-allow-origins='*' \
  --no-sandbox \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  --disable-gpu \
  --disable-background-networking \
  --disable-component-update \
  --disable-session-crashed-bubble \
  --disable-features=Translate,MediaRouter \
  --autoplay-policy=no-user-gesture-required \
  --disable-infobars \
  --simulate-outdated-no-au='Tue, 31 Dec 2099 23:59:59 GMT' \
  --user-data-dir=/tmp/kvtuber-live-demo-chrome-profile \
  --window-position=0,0 \
  --window-size=1440,900 \
  'http://127.0.0.1:18308/admin?token=kurage-admin' \
  2>&1 | tee /tmp/kvtuber-live-demo-tmuxlike/chrome.tty.log
```

Confirm CDP:

```bash
curl -sS http://127.0.0.1:9223/json/version | jq -r .Browser
```

## Recording Rule

Do not start ffmpeg right after the admin button click. The current seminar uses
LLM generation first, then TTS. A valid recording starts only after
`kurage_live.monitor` has non-silent audio.

Use a probe loop:

```bash
/usr/bin/ffmpeg -hide_banner -y \
  -f pulse -i kurage_live.monitor \
  -t 2 \
  -af volumedetect \
  -f null -
```

Only start final capture when `mean_volume` is above about `-55 dB`. The
successful rerun started after a probe returned `mean_volume: -19.0 dB`.

Capture:

```bash
/usr/bin/ffmpeg -y \
  -f x11grab -thread_queue_size 1024 \
  -video_size 1440x900 -framerate 30 -i :99.0 \
  -f pulse -thread_queue_size 1024 -i kurage_live.monitor \
  -t 30 \
  -c:v libx264 -preset veryfast -crf 21 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -ar 44100 -ac 2 \
  -movflags +faststart live_capture.mp4
```

Final crop used for `dd456c7c59e34fe5`:

```bash
/usr/bin/ffmpeg -y -i live_capture.mp4 \
  -vf "crop=1440:810:0:45,scale=1280:720,setsar=1" \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -ar 44100 -ac 2 \
  -movflags +faststart final_16x9.mp4
```

## Verification

Required checks before publishing:

```bash
/usr/bin/ffmpeg -hide_banner -i final_16x9.mp4 \
  -af volumedetect -f null -

/usr/bin/ffmpeg -y -ss 5 -i final_16x9.mp4 \
  -frames:v 1 final_preview.jpg
```

The fixed successful rerun verified as:

- Duration: `30.018` seconds
- Mean volume: `-17.4 dB`
- Max volume: `-3.1 dB`
- Preview: white viewer, readable seminar text, Kurage avatar at bottom right

## Do Not Publish

Do not publish any recording if:

- `mean_volume` is `-91 dB`
- the browser shows `127.0.0.1 refused to connect`
- the viewer text is empty
- the top of the seminar text is cut off
- the video was made from fake narration instead of real viewer audio
