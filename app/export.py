"""録画(raw.mp4) + シーン整列ナレーション + 字幕オーバーレイ → 16:9/9:16 書き出し。

融合点:
- B1: mark時刻でシーン分割し、各シーンの尺をナレーション長に合わせて整列
       (映像が短ければ最終フレームを保持 / 長ければそのまま=ナレに無音余白)
- B3: overlay ブロックを drawtext で焼き込み
- B4: 同一マスタから 16:9 と 9:16(Kurageショート) を書き出し
"""
import json, subprocess, tempfile
from pathlib import Path

from . import config, scenes as scenes_mod

CLIP_FPS = 15


def _probe_dur(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _placement_xy(placement: str) -> tuple[str, str]:
    m = {
        "top-left": ("60", "60"),
        "top-center": ("(w-text_w)/2", "60"),
        "top-right": ("w-text_w-60", "60"),
        "bottom-left": ("60", "h-text_h-80"),
        "bottom-center": ("(w-text_w)/2", "h-text_h-80"),
        "bottom-right": ("w-text_w-60", "h-text_h-80"),
        "center": ("(w-text_w)/2", "(h-text_h)/2"),
    }
    return m.get(placement, m["bottom-center"])


def _drawtext(overlay: dict, textfile: Path, fontsize: int) -> str:
    x, y = _placement_xy(overlay.get("placement", "bottom-center"))
    big = overlay.get("type") in ("title-card", "headline-card")
    fs = int(fontsize * (1.6 if big else 1.0))
    return (
        f"drawtext=fontfile='{config.FONT}':textfile='{textfile}':"
        f"fontcolor=white:fontsize={fs}:line_spacing=10:"
        f"box=1:boxcolor=black@0.55:boxborderw=18:x={x}:y={y}"
    )


def _build_scene_clips(run_dir: Path, scenes: list[dict], marks: list[dict],
                       raw: Path, tmp: Path) -> list[Path]:
    vdur = _probe_dur(raw)
    by_name = {m["name"]: m["t"] for m in marks}
    clips = []
    for i, s in enumerate(scenes):
        name = s["scene"]
        start = min(max(float(by_name.get(name, 0.0)), 0.0), max(vdur - 0.1, 0.0))
        # 次シーンのmarkまで、無ければ動画末尾まで
        nxt = None
        for j in range(i + 1, len(scenes)):
            if scenes[j]["scene"] in by_name:
                nxt = by_name[scenes[j]["scene"]]
                break
        end = min(float(nxt) if nxt is not None else vdur, vdur)
        if end <= start:
            end = min(vdur, start + 0.2)
        seg = max(0.2, end - start)
        adur = float(s.get("audio_dur") or 0.0)
        target = max(seg, adur, 1.2)
        pad = max(0.0, target - seg)

        clip = tmp / f"clip{i:03d}.mp4"
        ov = s.get("overlay")
        vf_parts = [
            f"trim=start={start:.3f}:duration={seg:.3f}",
            "setpts=PTS-STARTPTS",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        ]
        if pad > 0.01:
            vf_parts.append(f"tpad=stop_mode=clone:stop_duration={pad:.3f}")
        if ov and ov.get("text"):
            tf = tmp / f"ov{i:03d}.txt"
            tf.write_text(ov["text"])
            vf_parts.append(_drawtext(ov, tf, fontsize=34))
        vf = ",".join(vf_parts)

        audio = s.get("audio")
        cmd = [config.FFMPEG_BIN, "-y", "-i", str(raw)]
        if audio:
            cmd += ["-i", str(audio)]
            filt = f"[0:v]{vf}[v];[1:a]asetpts=PTS-STARTPTS,apad[a]"
        else:
            cmd += ["-f", "lavfi", "-t", f"{target:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
            filt = f"[0:v]{vf}[v];[1:a]asetpts=PTS-STARTPTS,anull[a]"
        cmd += [
            "-filter_complex", filt, "-map", "[v]", "-map", "[a]",
            "-t", f"{target:.3f}", "-r", str(CLIP_FPS),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-video_track_timescale", "15360", str(clip),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        clips.append(clip)
    return clips


def _concat(clips: list[Path], out: Path, tmp: Path):
    lst = tmp / "concat.txt"
    lst.write_text("\n".join(f"file '{c.resolve()}'" for c in clips) + "\n")
    subprocess.run([
        config.FFMPEG_BIN, "-y", "-fflags", "+genpts",
        "-f", "concat", "-safe", "0", "-i", str(lst),
        "-vf", "setpts=PTS-STARTPTS",
        "-af", "asetpts=PTS-STARTPTS",
        "-r", str(CLIP_FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", str(out),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _reformat(master: Path, out: Path, w: int, h: int):
    """マスタを指定アスペクトに fit(レターボックス) して書き出し。"""
    dur = max(_probe_dur(master), 0.1)
    vf = ("tpad=stop_mode=clone:stop_duration=120,"
          f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    subprocess.run([
        config.FFMPEG_BIN, "-y", "-i", str(master), "-vf", vf, "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-movflags", "+faststart", str(out),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def export(run_dir: Path, formats: list[str] = None) -> dict:
    run_dir = Path(run_dir)
    formats = formats or config.EXPORT_FORMATS
    scenes = scenes_mod.load(run_dir / "scenes.json")
    marks = json.loads((run_dir / "marks.json").read_text())
    raw = run_dir / "raw.mp4"

    results = {}
    with tempfile.TemporaryDirectory(dir=run_dir) as td:
        tmp = Path(td)
        clips = _build_scene_clips(run_dir, scenes, marks, raw, tmp)
        master = run_dir / "master.mp4"
        _concat(clips, master, tmp)
        results["master"] = str(master)

        for fmt in formats:
            if fmt == "16:9":
                w, h = config.HORZ_W, config.HORZ_H
            elif fmt == "9:16":
                w, h = config.VERT_W, config.VERT_H
            else:
                continue
            out = run_dir / f"final_{fmt.replace(':', 'x')}.mp4"
            _reformat(master, out, w, h)
            results[fmt] = str(out)
    return results
