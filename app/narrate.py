"""シーンごとに Kurageの声(edge-tts 日本語)でナレーション音声を生成 (B1+C2)。

各clipの実長(秒)を測り、後段(export)でmark時刻に整列させる土台にする。
TTSはローカル不要のedge-tts(無料)。Kurageと同じ ja-JP-NanamiNeural。
"""
import asyncio, json, subprocess
from pathlib import Path

import edge_tts

from . import config, scenes as scenes_mod


def _probe_dur(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


async def _tts_one(text: str, voice: str, rate: str, out_path: Path):
    comm = edge_tts.Communicate(text, voice=voice, rate=rate)
    await comm.save(str(out_path))


async def synth(run_dir: Path) -> dict:
    """run_dir/scenes.json の各シーンに音声を生成し scenes に audio/audio_dur を書き戻す。"""
    run_dir = Path(run_dir)
    audio_dir = run_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    scenes = scenes_mod.load(run_dir / "scenes.json")

    for i, s in enumerate(scenes):
        if s.get("audio_source") == "original":
            s["audio"], s["audio_dur"] = None, 0.0
            continue
        text = (s.get("text") or "").strip()
        if not text:
            s["audio"], s["audio_dur"] = None, 0.0
            continue
        voice = s.get("voice") or config.TTS_VOICE
        wav = audio_dir / f"{s['scene']}.mp3"
        await _tts_one(text, voice, config.TTS_RATE, wav)
        s["audio"] = str(wav)
        s["audio_dur"] = round(_probe_dur(wav), 3)

    scenes_mod.save(run_dir / "scenes.json", scenes)
    return {"scenes": scenes,
            "total_audio": round(sum(s.get("audio_dur", 0) for s in scenes), 2)}


def synth_sync(run_dir: Path) -> dict:
    return asyncio.run(synth(run_dir))
