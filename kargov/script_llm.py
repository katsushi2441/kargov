"""OAuth Claude でナレーション台本を整文 (C1の仕上げ)。

url2ai/ustory.php・kuragevp と同じ流儀:
  claude -p --output-format text --permission-mode dontAsk --model <model> "<prompt>"
(APIキー不要。vscode-server拡張のnative-binaryを使う)

入力: agent_run が作った scenes.json（gemma4の生next_goal=英語混じり）
出力: 各シーンを「自然な日本語ナレーション」+「短い字幕」に書き換えて scenes.json へ反映。
intro/outro はユーザ指定の確定文なので対象外。
"""
import glob, os, re, subprocess
from pathlib import Path

from . import config, scenes as scenes_mod

SEP = "@@@"
_NUM_RE = re.compile(r"^\s*(\d+)[\.\)、:：]\s*(.*)$")


def resolve_claude_bin() -> str:
    candidates = []
    if config.CLAUDE_BIN:
        candidates.append(config.CLAUDE_BIN)
    import shutil
    found = shutil.which("claude")
    if found:
        candidates.append(found)
    versioned = sorted(glob.glob(
        str(Path.home()) + "/.vscode-server/extensions/"
        "anthropic.claude-code-*/resources/native-binary/claude"))
    candidates.extend(reversed(versioned))   # 新しいバージョン優先
    for p in candidates:
        if p and Path(p).exists() and os.access(p, os.X_OK):
            return p
    return ""


def claude_request(prompt: str) -> str:
    claude_bin = resolve_claude_bin()
    if not claude_bin:
        return ""
    cmd = [claude_bin, "-p", "--output-format", "text",
           "--permission-mode", "dontAsk", "--model", config.CLAUDE_MODEL, prompt]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=config.CLAUDE_TIMEOUT, check=False)
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _build_prompt(items: list[dict], topic: str) -> str:
    numbered = "\n".join(
        f"{i}. [{s['scene']}] {s['text']}" for i, s in enumerate(items, 1))
    return (
        "あなたは製品デモ動画のプロのナレーション作家です。\n"
        "以下は、AIエージェントがWeb画面を自律操作した各ステップの『操作意図メモ』"
        "（英語混じり・機械的）です。これを視聴者向けの自然な日本語ナレーションに書き換えてください。\n\n"
        f"動画のテーマ: {topic}\n\n"
        "手順（内部で考え、最終結果だけ出力）:\n"
        "1. 各ステップが画面上で何をしているかを把握する\n"
        "2. 視聴者が操作の流れを理解できる、話し言葉の日本語ナレーションにする\n"
        "3. 各シーンに、画面に出す短い字幕（20文字以内）も付ける\n\n"
        "厳守ルール:\n"
        "- 出力は番号付きで、入力と同じ行数・同じ番号を厳守（増減・統合禁止）\n"
        f"- 各行の形式: 「N. <ナレーション文> {SEP} <字幕20字以内>」\n"
        "- ナレーションは1文〜2文、各行50〜90文字程度。説明・前置き・原文は書かない\n"
        "- 専門用語は噛み砕き、機械翻訳調を避け、デモとして魅力的に\n"
        f"- 区切りは必ず {SEP} を使う\n\n"
        f"ステップ:\n{numbered}\n"
    )


def _parse(raw: str, n: int) -> list[tuple[str, str]] | None:
    out = {}
    for line in raw.splitlines():
        m = _NUM_RE.match(line)
        if not m:
            continue
        idx = int(m.group(1))
        body = m.group(2)
        if SEP in body:
            narr, cap = body.split(SEP, 1)
        else:
            narr, cap = body, body
        out[idx] = (narr.strip(), cap.strip()[:24])
    if len(out) < n:
        return None
    return [out[i] for i in range(1, n + 1)]


def refine(run_dir: Path, topic: str = "AIエージェントによるWeb操作デモ") -> dict:
    run_dir = Path(run_dir)
    scenes = scenes_mod.load(run_dir / "scenes.json")
    # intro/outro は確定文なので対象外
    targets = [s for s in scenes if s["scene"] not in ("intro", "outro")]
    if not targets:
        return {"refined": 0, "ok": True}

    raw = claude_request(_build_prompt(targets, topic))
    parsed = _parse(raw, len(targets)) if raw else None
    if not parsed:
        return {"refined": 0, "ok": False,
                "note": "Claude整文に失敗（生テキスト維持）"}

    for s, (narr, cap) in zip(targets, parsed):
        if narr:
            s["text"] = narr
            if s.get("overlay") is not None:
                s["overlay"]["text"] = cap or narr[:20]
    scenes_mod.save(run_dir / "scenes.json", scenes)
    return {"refined": len(parsed), "ok": True}
