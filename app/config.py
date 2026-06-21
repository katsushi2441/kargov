"""kargov 全体の既定値・パス。環境変数で上書き可。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.environ.get("KARGOV_RUNS", ROOT / "runs"))
ASSETS_DIR = ROOT / "assets"

# --- ポート方針: 18300番台の空き最若 ---
PREVIEW_PORT = int(os.environ.get("KARGOV_PORT", "18308"))

# --- ブラウザ/録画 ---
CHROME_BIN = os.environ.get("KARGOV_CHROME", "/usr/bin/google-chrome")
FFMPEG_BIN = os.environ.get("KARGOV_FFMPEG", "/usr/bin/ffmpeg")  # x11grab/フィルタ完備のapt版
DEBUG_PORT = int(os.environ.get("KARGOV_DEBUG_PORT", "9233"))
REC_WIDTH = int(os.environ.get("KARGOV_W", "1280"))
REC_HEIGHT = int(os.environ.get("KARGOV_H", "720"))
SCREENCAST_QUALITY = int(os.environ.get("KARGOV_JPEG_Q", "80"))

# --- AV録画 (Xvfb + Pulse + ffmpeg) ---
AV_DISPLAY = os.environ.get("KARGOV_AV_DISPLAY", ":97")
AV_FPS = int(os.environ.get("KARGOV_AV_FPS", "15"))
AV_PULSE_SINK = os.environ.get("KARGOV_AV_PULSE_SINK", "kurage_live")

# --- LLM (ローカル Ollama) ---
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("KARGOV_MODEL", "gemma4:12b-it-qat")
OLLAMA_TIMEOUT = int(os.environ.get("KARGOV_LLM_TIMEOUT", "600"))

# --- ナレ整文 (OAuth Claude, url2ai/ustory.php・kuragevpと同方式) ---
CLAUDE_BIN = os.environ.get("KARGOV_CLAUDE_BIN", "")     # 空ならvscode-serverから自動解決
CLAUDE_MODEL = os.environ.get("KARGOV_CLAUDE_MODEL", "sonnet")
CLAUDE_TIMEOUT = int(os.environ.get("KARGOV_CLAUDE_TIMEOUT", "240"))

# --- TTS (Kurageの声 = edge-tts 日本語) ---
TTS_VOICE = os.environ.get("KARGOV_VOICE", "ja-JP-NanamiNeural")  # Kurageと同じ
TTS_RATE = os.environ.get("KARGOV_TTS_RATE", "+0%")

# --- 書き出し ---
EXPORT_FORMATS = ["16:9", "9:16"]   # B4: 縦横
FADE_MS = int(os.environ.get("KARGOV_FADE_MS", "600"))
GAP_SPEED = float(os.environ.get("KARGOV_GAP_SPEED", "2.0"))

# 9:16 ショートの基準解像度 (Kurage動画と揃える)
VERT_W, VERT_H = 576, 1024
HORZ_W, HORZ_H = 1280, 720

FONT = os.environ.get(
    "KARGOV_FONT",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
)
