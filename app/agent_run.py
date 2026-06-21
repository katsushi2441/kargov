"""自律操作で録画しつつ scenes.json ドラフトを自動生成 (C1 = 融合の核)。

browser-use(ローカルgemma4)がWeb UIを自分で操作し、各ステップ境界で recorder.mark() を打つ。
同時に「そのステップで何をしたか」をナレーション文のドラフトとして scenes に積む。
Argoは台本を手書き必須だが、kargovは "AIが操作しながら台本も書く"。
"""
import asyncio, os, re, time
from pathlib import Path

os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("BROWSER_USE_CLOUD_SYNC", "false")

from browser_use import Agent, BrowserProfile, ChatOllama

from . import config, chrome, scenes as scenes_mod
from .recorder import ScreencastRecorder
from .recorder_av import AVRecorder


def _summarize_step(step_idx: int, model_output) -> tuple[str, str]:
    """browser-useのステップ出力から (シーン名, ナレ文ドラフト) を作る。

    next_goal / アクションのテキストを拾ってナレーション草案にする。LLM整文は後段(narrate)で。
    """
    goal = ""
    try:
        goal = (getattr(model_output, "current_state", None)
                and model_output.current_state.next_goal) or ""
    except Exception:
        goal = ""
    goal = re.sub(r"\s+", " ", str(goal)).strip()
    name = f"step{step_idx:02d}"
    text = goal or f"ステップ{step_idx}の操作を実行します。"
    return name, text


async def run(task: str, url: str = "", out: Path = None,
              steps: int = 20, cookies: list[dict] | None = None,
              headless: bool = True, intro: str = "", outro: str = "",
              audio: bool = False) -> dict:
    out = Path(out or (config.RUNS_DIR / ("run_" + time.strftime("%Y%m%d_%H%M%S"))))
    out.mkdir(parents=True, exist_ok=True)
    port = config.DEBUG_PORT

    rec = None
    if audio:
        rec = AVRecorder(port, out)
        proc = rec.start(url or "about:blank")
        headless = False
    else:
        proc = chrome.launch(port, headless=headless)
    try:
        await asyncio.sleep(3)
        if cookies:
            await chrome.set_cookies(port, cookies)

        if rec is None:
            rec = ScreencastRecorder(port, out)
            rec.start()
        await asyncio.sleep(0.5)

        draft: list[dict] = []
        if intro:
            rec.mark("intro")
            draft.append({"scene": "intro", "text": intro,
                          "overlay": {"type": "title-card", "text": intro,
                                      "placement": "center"}})

        seen = {"i": 0}

        async def on_step_end(agent_obj):
            seen["i"] += 1
            i = seen["i"]
            mo = getattr(agent_obj, "state", None)
            model_output = None
            try:
                model_output = agent_obj.history.history[-1].model_output
            except Exception:
                model_output = None
            name, text = _summarize_step(i, model_output)
            rec.mark(name)
            draft.append({
                "scene": name, "text": text,
                "overlay": {"type": "lower-third", "text": text[:40],
                            "placement": "bottom-center"},
            })
            # ステップ毎のスクショも保存(プレビュー用)
            try:
                shot = await agent_obj.browser_session.take_screenshot()
                if shot:
                    (out / f"step{i:02d}.png").write_bytes(
                        shot if isinstance(shot, bytes) else bytes(shot))
            except Exception:
                pass

        llm = ChatOllama(model=config.OLLAMA_MODEL, host=config.OLLAMA_HOST,
                         timeout=config.OLLAMA_TIMEOUT)
        profile = BrowserProfile(cdp_url=f"http://127.0.0.1:{port}", headless=headless)
        full_task = task if (audio or not url) else f"まず {url} を開いてください。\n{task}"
        agent = Agent(task=full_task, llm=llm, browser_profile=profile,
                      max_actions_per_step=3)
        history = await agent.run(max_steps=steps, on_step_end=on_step_end)

        if outro:
            rec.mark("outro")
            draft.append({"scene": "outro", "text": outro,
                          "overlay": {"type": "title-card", "text": outro,
                                      "placement": "center"}})

        await asyncio.sleep(1)
        raw_mp4 = await rec.stop_and_encode(out / "raw.mp4")

        scenes_mod.save(out / "scenes.json", draft)
        (out / "marks.json").write_text(
            __import__("json").dumps(rec.marks, ensure_ascii=False, indent=2))
        (out / "agent_result.txt").write_text(str(history.final_result() or ""))

        return {"out": str(out), "raw_mp4": str(raw_mp4),
                "scenes": str(out / "scenes.json"),
                "marks": rec.marks, "n_frames": len(rec.frame_times),
                "duration": rec.duration}
    finally:
        if hasattr(rec, "close"):
            rec.close()
        else:
            proc.terminate()
