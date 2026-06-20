"""Create a short demo-ready run by trimming long browser recordings.

The recorder keeps raw browser video plus scene marks. This module creates a new
run directory that contains only the useful marked intervals, with adjusted marks
so the existing narrate/export pipeline can produce a polished demo video.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import config, scenes as scenes_mod

_SKIP_RE = re.compile(
    r"\b(wait|waiting|observe|extract|finalize|call done|requirements have been met)\b",
    re.IGNORECASE,
)


def _probe_dur(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _mark_map(marks: list[dict]) -> dict[str, float]:
    return {str(mark["name"]): float(mark["t"]) for mark in marks if "name" in mark}


def _next_mark_time(name: str, ordered_names: list[str], by_name: dict[str, float], raw_dur: float) -> float:
    try:
        idx = ordered_names.index(name)
    except ValueError:
        return raw_dur
    for next_name in ordered_names[idx + 1 :]:
        if next_name in by_name:
            return by_name[next_name]
    return raw_dur


def _pick_scenes(scenes: list[dict], max_steps: int) -> list[dict]:
    intro = [scene for scene in scenes if scene.get("scene") == "intro"][:1]
    outro = [scene for scene in scenes if scene.get("scene") == "outro"][:1]
    body: list[dict] = []

    for scene in scenes:
        name = scene.get("scene")
        if name in ("intro", "outro"):
            continue
        body.append(scene)
        if len(body) >= max_steps:
            break

    # If the agent kept observing after the useful flow, those late bookkeeping
    # scenes are naturally excluded by max_steps. Keep early scenes even when the
    # model describes them as "wait", because the screen may already show the
    # important product state.
    return intro + body + outro


def _extract_clip(raw: Path, start: float, duration: float, clip: Path) -> None:
    subprocess.run(
        [
            config.FFMPEG_BIN,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(raw),
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _concat(clips: list[Path], out: Path, tmp: Path) -> None:
    concat_file = tmp / "concat.txt"
    concat_file.write_text("\n".join(f"file '{clip.resolve()}'" for clip in clips) + "\n")
    subprocess.run(
        [
            config.FFMPEG_BIN,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(out),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def summarize(
    run_dir: Path,
    out_dir: Path | None = None,
    target_seconds: int = 75,
    max_steps: int = 4,
    max_segment_seconds: float = 8.0,
) -> dict:
    run_dir = Path(run_dir)
    raw = run_dir / "raw.mp4"
    marks = json.loads((run_dir / "marks.json").read_text())
    scenes = scenes_mod.load(run_dir / "scenes.json")
    raw_dur = _probe_dur(raw)
    by_name = _mark_map(marks)
    ordered_names = [str(mark["name"]) for mark in marks if "name" in mark]
    selected = [scene for scene in _pick_scenes(scenes, max_steps) if scene.get("scene") in by_name]

    out_dir = Path(out_dir or (run_dir.parent / f"{run_dir.name}_short"))
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    tmp = out_dir / "segments"
    tmp.mkdir()

    clips: list[Path] = []
    new_marks: list[dict] = []
    elapsed = 0.0
    budget_per_scene = max(2.0, min(max_segment_seconds, target_seconds / max(len(selected), 1)))

    for index, scene in enumerate(selected):
        name = str(scene["scene"])
        start = by_name[name]
        next_time = _next_mark_time(name, ordered_names, by_name, raw_dur)
        available = max(0.2, next_time - start)
        duration = min(available, budget_per_scene)
        if name in ("intro", "outro"):
            duration = min(available, max(2.0, budget_per_scene * 0.6))
        clip = tmp / f"seg{index:03d}_{name}.mp4"
        _extract_clip(raw, start, duration, clip)
        clips.append(clip)
        new_marks.append({"name": name, "t": round(elapsed, 3)})
        elapsed += _probe_dur(clip) or duration

    if not clips:
        raise RuntimeError("no scenes selected for summary")

    short_raw = out_dir / "raw.mp4"
    _concat(clips, short_raw, tmp)
    scenes_mod.save(out_dir / "scenes.json", selected)
    (out_dir / "marks.json").write_text(json.dumps(new_marks, ensure_ascii=False, indent=2) + "\n")
    if (run_dir / "agent_result.txt").exists():
        shutil.copy2(run_dir / "agent_result.txt", out_dir / "agent_result.txt")

    return {
        "out": str(out_dir),
        "raw_mp4": str(short_raw),
        "scenes": str(out_dir / "scenes.json"),
        "marks": new_marks,
        "selected": [scene["scene"] for scene in selected],
        "duration": round(_probe_dur(short_raw), 3),
    }
