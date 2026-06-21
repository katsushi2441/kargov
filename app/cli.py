"""kargov CLI (argo風コマンド)。

  kargov record  --task "..." [--url U] [--cookie NAME=VAL@domain] [--intro ..] [--outro ..]
  kargov narrate <run_dir>
  kargov export  <run_dir> [--formats 16:9,9:16]
  kargov pipeline --task "..." [...]          record→narrate→export を一気通貫
  kargov validate <run_dir>
  kargov summarize <run_dir>
  kargov doctor
"""
import argparse, asyncio, json, shutil, subprocess, sys
from pathlib import Path

from . import config, scenes as scenes_mod
from . import agent_run, narrate, export as export_mod, script_llm, summarize as summarize_mod


def _parse_cookies(specs: list[str]) -> list[dict]:
    """--cookie NAME=VALUE@domain を CDP cookie dict に。"""
    out = []
    for sp in specs or []:
        nv, _, dom = sp.partition("@")
        name, _, val = nv.partition("=")
        if name and val and dom:
            out.append({"name": name, "value": val, "domain": dom})
    return out


def cmd_record(a):
    cookies = _parse_cookies(a.cookie)
    res = asyncio.run(agent_run.run(
        task=a.task, url=a.url, out=a.out, steps=a.steps,
        cookies=cookies, headless=not a.headful, intro=a.intro, outro=a.outro,
        audio=a.audio))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return res


def cmd_refine(a):
    res = script_llm.refine(a.run_dir, topic=a.topic or
                            "AIエージェントによるWeb操作デモ")
    if res["ok"]:
        print(f"ナレ整文(OAuth Claude): {res['refined']}シーンを日本語化")
    else:
        print("整文スキップ:", res.get("note"))


def cmd_narrate(a):
    res = narrate.synth_sync(a.run_dir)
    print(f"ナレーション生成: {len(res['scenes'])}シーン / 合計{res['total_audio']}秒")


def cmd_export(a):
    fmts = a.formats.split(",") if a.formats else None
    res = export_mod.export(a.run_dir, formats=fmts)
    print(json.dumps(res, ensure_ascii=False, indent=2))



def cmd_summarize(a):
    res = summarize_mod.summarize(
        a.run_dir,
        out_dir=a.out,
        target_seconds=a.target_seconds,
        max_steps=a.max_steps,
        max_segment_seconds=a.max_segment_seconds,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))


def cmd_validate(a):
    run_dir = Path(a.run_dir)
    scns = scenes_mod.load(run_dir / "scenes.json")
    marks = None
    mp = run_dir / "marks.json"
    if mp.exists():
        marks = json.loads(mp.read_text())
    errs = scenes_mod.validate(scns, marks)
    if errs:
        print("NG:")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    print(f"OK: {len(scns)}シーン、整合性に問題なし")


def cmd_pipeline(a):
    res = cmd_record(a)
    run_dir = Path(res["out"])
    if not a.no_refine:
        r = script_llm.refine(run_dir, topic=a.topic or a.task)
        print("ナレ整文(OAuth Claude):",
              f"{r['refined']}シーン日本語化" if r["ok"] else r.get("note"))
    narrate.synth_sync(run_dir)
    fmts = a.formats.split(",") if a.formats else None
    out = export_mod.export(run_dir, formats=fmts)
    print("=== PIPELINE DONE ===")
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_doctor(a):
    print("kargov doctor")
    print("  ffmpeg :", config.FFMPEG_BIN,
          "OK" if Path(config.FFMPEG_BIN).exists() else "NG")
    has_xfade = subprocess.run([config.FFMPEG_BIN, "-hide_banner", "-filters"],
                               capture_output=True, text=True).stdout
    print("    xfade :", "OK" if "xfade" in has_xfade else "NG",
          "/ drawtext :", "OK" if "drawtext" in has_xfade else "NG")
    print("  ffprobe:", "OK" if shutil.which("ffprobe") else "NG")
    print("  chrome :", config.CHROME_BIN,
          "OK" if Path(config.CHROME_BIN).exists() else "NG")
    print("  font   :", config.FONT, "OK" if Path(config.FONT).exists() else "NG")
    try:
        import urllib.request
        urllib.request.urlopen(config.OLLAMA_HOST + "/api/tags", timeout=3)
        print("  ollama :", config.OLLAMA_HOST, "OK /", config.OLLAMA_MODEL)
    except Exception as e:
        print("  ollama : NG", e)


def build_parser():
    p = argparse.ArgumentParser(prog="kargov")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_record_args(sp):
        sp.add_argument("--task", required=True)
        sp.add_argument("--url", default="")
        sp.add_argument("--out", default="")
        sp.add_argument("--steps", type=int, default=20)
        sp.add_argument("--cookie", action="append", default=[],
                        help="NAME=VALUE@domain （複数可）")
        sp.add_argument("--headful", action="store_true")
        sp.add_argument("--audio", action="store_true",
                        help="Xvfb+Pulse+ffmpegでブラウザ音声込み録画を行う")
        sp.add_argument("--intro", default="")
        sp.add_argument("--outro", default="")
        sp.add_argument("--formats", default="")
        sp.add_argument("--topic", default="", help="ナレ整文用の動画テーマ")
        sp.add_argument("--no-refine", action="store_true",
                        help="OAuth Claudeによるナレ整文をスキップ")

    sp = sub.add_parser("record"); add_record_args(sp); sp.set_defaults(fn=cmd_record)
    sp = sub.add_parser("pipeline"); add_record_args(sp); sp.set_defaults(fn=cmd_pipeline)
    sp = sub.add_parser("refine"); sp.add_argument("run_dir")
    sp.add_argument("--topic", default=""); sp.set_defaults(fn=cmd_refine)
    sp = sub.add_parser("narrate"); sp.add_argument("run_dir"); sp.set_defaults(fn=cmd_narrate)
    sp = sub.add_parser("export"); sp.add_argument("run_dir")
    sp.add_argument("--formats", default=""); sp.set_defaults(fn=cmd_export)
    sp = sub.add_parser("validate"); sp.add_argument("run_dir"); sp.set_defaults(fn=cmd_validate)
    sp = sub.add_parser("summarize"); sp.add_argument("run_dir")
    sp.add_argument("--out", type=Path, default=None)
    sp.add_argument("--target-seconds", type=int, default=75)
    sp.add_argument("--max-steps", type=int, default=4)
    sp.add_argument("--max-segment-seconds", type=float, default=8.0)
    sp.set_defaults(fn=cmd_summarize)
    sp = sub.add_parser("doctor"); sp.set_defaults(fn=cmd_doctor)
    return p


def main():
    args = build_parser().parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
