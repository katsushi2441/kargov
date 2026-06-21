# 作業依頼: kargovでkvtuberライブ配信（バイブコーディングセミナー）のデモ動画を作る

## ゴール
kargov（`/home/kojima/work/kargov`、自前のbrowser-use×録画ツール）を使って、
**kvtuber(aituber-onair)のライブ配信機能のデモ動画**を作る。

- 内容: browser-useが kvtuber の admin/live UI を操作して
  「バイブコーディングセミナー」のライブ配信を開始 → viewerでくらげが配信している様子を録画。
- 音声: **区間で使い分け**
  - 操作している区間 = kargovの解説ナレ（edge-tts / OAuth Claude整文）
  - 配信viewer区間 = **セミナーの本物の音声（くらげの声）をそのまま**
- 出力: 16:9 と 9:16、字幕焼き込み（kargovの既存export流用）

## 既に判明している事実（そのまま使える）
- aituber-onair: `/home/kojima/work/kvtuber/aituber-onair`、Vite dev server **:18308**稼働中。
- **admin token = `change-me`**（`KURAGE_ADMIN_TOKEN`。スクリプト側デフォルト`kurage-admin`はバグでズレてる→要修正）。
- 番組開始API（これは成功する）:
  ```
  curl -X POST "http://127.0.0.1:18308/control/start-program?token=change-me" \
    -H "Content-Type: application/json" \
    -d '{"programId":"vibe-coding-intro","autoplay":true}'
  # → {"ok":true,"clients":1,"program":{...}}
  ```
- 配信viewer: `http://127.0.0.1:18308/viewer?broadcast=1`、admin: `http://127.0.0.1:18308/admin?token=change-me`
- 番組: `vibe-coding-intro` / `-basic` / `-advanced`（storage/programs.json）
- TTSバックエンド `http://127.0.0.1:18308/kurage-tts/v1/audio/speech`（voice=ja-JP-NanamiNeural）は単体で正常に音声mp3を返す（-17.6dB）。
- 実機のライブ配信（`scripts/youtube-live-rtmp.mjs`, display **:98**, profile `/tmp/kurage-youtube-chrome-profile-98`）は**音声込みで成功している**（ユーザー談）。
  仕組み: pulse `module-null-sink`(kurage_live) を作り、Xvfb上のChrome(`PULSE_SINK=kurage_live`)で再生、
  `ffmpeg -f x11grab -i :98 -f pulse -i kurage_live.monitor ...` で取り込み→RTMP。

## 詰まっている点（ここを解決してほしい）
ローカル録画用に **別のXvfb(:97)＋profile-98のコピー＋null-sink** でviewerをキャプチャすると、
- viewerは kurage-tts を毎秒フェッチし、Web Audio（AudioBufferSourceNode→Gain→…→AudioDestinationNode）も処理中
- なのに **pulse sink に届く音が完全無音(-91dB)**
- sink-inputには `Google Chrome` と `speech-dispatcher-dummy` が出る

→ **「実機の動く配信(:98)が、どうやってpulseに実音を出しているか」を突き止め、その経路をローカルのファイル録画で再現**してほしい。
（候補: 実機はprofileコピーでなく実体を使う / 既存のpulse default sink / マスターGainの扱い / start-broadcast-program.mjsの正しい使い方 / そもそもRTMPの音声も無音だったなら viewer側の出力経路を修正、など）

## やってほしい実装
1. **音声付きローカル録画の確立**: 実機:98の動く構成を踏襲し、
   `Xvfb + pulse(null-sink) + Chrome(headful, --remote-debugging-port付き, PULSE_SINK) + ffmpeg(x11grab+pulse) → mp4(音声入り)` を、
   browser-useが相乗り操作できる形（`cdp_url`接続）で動かす。まず10〜15秒の録画で `volumedetect` が -91dB でない（実音がある）ことを確認。
2. **kargovに音声付き録画モードを追加**: `app/recorder_av.py`（上記をクラス化、mark対応）。
   `app/agent_run.py` に `audio=True` 経路（headlessのCDP screencastではなくAVRecorderを使う）。
3. **browser-useタスク**: `http://127.0.0.1:18308/admin?token=change-me` を開き、
   バイブコーディングセミナー番組を選んで配信開始 → `viewer?broadcast=1` を表示。
4. **export拡張**: sceneごとに `audio_source: "narration" | "original"`。
   - narration: 既存どおりedge-tts、映像をナレ長に整列
   - original: raw.mp4(音声入り)の該当区間の**元音声をそのまま**使う（配信viewer区間）
   `app/narrate.py` はoriginalシーンをスキップ。
5. **仕上げ**: intro/outro、字幕、16:9/9:16書き出し（既存export流用）。最後に kuragev.php 公開＋AIxSNS告知は任意。

## kargov 現状（参考）
- パッケージ: `app/`（config/recorder/chrome/agent_run/scenes/script_llm/narrate/export/summarize/cli）
- 実行: `cd /home/kojima/work/kargov && .venv/bin/kargov <cmd>`、`kargov doctor` 全OK
- 録画は現状 CDP `Page.startScreencast`（**映像のみ・音声なし**）。ここに音声経路を足すのが本件。
- ローカルLLM gemma4:12b-it-qat、ffmpegは `/usr/bin/ffmpeg`（x11grab/pulse対応確認済み）、font=Noto CJK。
