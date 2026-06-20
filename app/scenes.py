"""scenes.json マニフェスト (B2) と整合チェック (B8)。

スキーマ (1要素=1シーン):
{
  "scene": "step1",            # 一意なシーン名 = 録画中の mark 名と対応
  "text": "ここで動画URLを…",   # ナレーション文 (TTSで読み上げ)
  "voice": "ja-JP-NanamiNeural",   # 省略時は config.TTS_VOICE
  "overlay": {                  # 任意。画面に出す字幕ブロック (B3)
    "type": "lower-third", "text": "URLを入力", "placement": "bottom-center"
  }
}
"""
import json
from pathlib import Path

from . import config

OVERLAY_TYPES = {"lower-third", "headline-card", "callout", "caption", "title-card"}
PLACEMENTS = {"top-left", "top-center", "top-right",
              "bottom-left", "bottom-center", "bottom-right", "center"}


def load(path) -> list[dict]:
    return json.loads(Path(path).read_text())


def save(path, scenes: list[dict]):
    Path(path).write_text(json.dumps(scenes, ensure_ascii=False, indent=2) + "\n")


def validate(scenes: list[dict], marks: list[dict] | None = None) -> list[str]:
    """問題点を文字列リストで返す。空なら健全 (B8)。"""
    errs = []
    names = [s.get("scene") for s in scenes]
    if len(names) != len(set(names)):
        errs.append("シーン名が重複しています")
    for i, s in enumerate(scenes):
        if not s.get("scene"):
            errs.append(f"[{i}] scene 名がありません")
        if not s.get("text"):
            errs.append(f"[{s.get('scene', i)}] text(ナレーション)が空です")
        ov = s.get("overlay")
        if ov:
            if ov.get("type") not in OVERLAY_TYPES:
                errs.append(f"[{s.get('scene')}] overlay.type 不正: {ov.get('type')}")
            pl = ov.get("placement", "bottom-center")
            if pl not in PLACEMENTS:
                errs.append(f"[{s.get('scene')}] overlay.placement 不正: {pl}")
    if marks is not None:
        mark_names = {m["name"] for m in marks}
        for n in names:
            if n not in mark_names:
                errs.append(f"シーン '{n}' に対応する録画markがありません")
    return errs
