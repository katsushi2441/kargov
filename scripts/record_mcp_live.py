#!/usr/bin/env python3
"""行政の MCP と自社の MCP を並べて使う AI エージェントを、実際に動かしている画面ごと録画する。

作り物の再生ではない: kbousai/demo/live のビューア（http://127.0.0.1:18348/）の「実行」を本物のマウスで押し、
本当に claude -p が2つの MCP を呼んでいる間を CDP Screencast で録る。シーンの区切り（mark）とナレーションは、
画面に実際に出た呼び出し（当社 MCP の初回・国交省 MCP の呼び出し・回答）から作る。

  cd /home/kojima/work/kargov && .venv/bin/python scripts/record_mcp_live.py
  → runs/mcp_live_<日時>/raw.mp4・marks.json・scenes.json
  そのあと: .venv/bin/python -m kargov.cli narrate <run> && .venv/bin/python -m kargov.cli export <run>
"""
import asyncio
import datetime
import json
import sys
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import chrome, config  # noqa: E402
from app.recorder import ScreencastRecorder, page_ws  # noqa: E402

VIEWER = "http://127.0.0.1:18348/"
PORT = config.DEBUG_PORT


class CDP:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, method, **params):
        self.n += 1
        mid = self.n
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            m = json.loads(await self.ws.recv())
            if m.get("id") == mid:
                return m.get("result", {})

    async def ev(self, js):
        r = await self.call("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    async def click(self, css):
        x, y = await self.ev(f"(()=>{{const b=document.querySelector('{css}').getBoundingClientRect();"
                             f"return [b.x+b.width/2,b.y+b.height/2]}})()")
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            await self.call("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)
            await asyncio.sleep(0.05)


async def main():
    out = ROOT / "runs" / f"mcp_live_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    out.mkdir(parents=True)
    proc = chrome.launch(PORT, headless=True)
    try:
        async with websockets.connect(await page_ws(PORT), max_size=None) as ws:
            c = CDP(ws)
            await c.call("Page.enable")
            # 窓の枠ぶん画面が縮んで上下に黒帯が出るので、描画の大きさを録画の大きさにそろえる
            await c.call("Emulation.setDeviceMetricsOverride", width=config.REC_WIDTH, height=config.REC_HEIGHT,
                         deviceScaleFactor=1, mobile=False)
            await c.call("Page.navigate", url=VIEWER)
            await asyncio.sleep(3)
            rec = ScreencastRecorder(PORT, out)
            rec.start()
            await asyncio.sleep(1.0)
            rec.mark("intro"); await asyncio.sleep(6)
            rec.mark("question"); await asyncio.sleep(6)
            await c.click("#go")
            rec.mark("run")
            seen_m, labels, marks_m = 0, [], []
            k_marked = False
            for _ in range(900):                       # 最長 15 分
                d = await c.ev("JSON.stringify({k:demo.k,m:demo.m,done:demo.done,"
                               "calls:[...document.querySelectorAll('.call.m .t')].map(e=>e.innerText)})")
                d = json.loads(d)
                if d["k"] and not k_marked:
                    rec.mark("kbousai"); k_marked = True
                while seen_m < d["m"]:
                    seen_m += 1
                    lab = d["calls"][seen_m - 1] if seen_m - 1 < len(d["calls"]) else ""
                    labels.append(lab)
                    if seen_m == 1 or seen_m % 4 == 0:   # 4回に1回、場面を区切る（ナレーションが追いつく間隔）
                        name = f"mlit{seen_m:02d}"
                        rec.mark(name); marks_m.append((name, seen_m))
                if d["done"]:
                    break
                await asyncio.sleep(1)
            rec.mark("answer")
            # 回答の欄を、読める速さで下までスクロールする
            for _ in range(40):
                await c.ev("(()=>{const a=document.getElementById('answer');a.scrollTop+=a.clientHeight*0.12;return 1})()")
                await asyncio.sleep(0.6)
            rec.mark("outro"); await asyncio.sleep(7)
            await rec.stop_and_encode(out / "raw.mp4")
            (out / "marks.json").write_text(json.dumps(rec.marks, ensure_ascii=False, indent=1))
            (out / "events.json").write_text(json.dumps({"mlit_labels": labels, "mlit_marks": marks_m,
                                                         "k": d["k"], "m": d["m"]}, ensure_ascii=False, indent=1))
    finally:
        proc.terminate()
    print(out)


if __name__ == "__main__":
    asyncio.run(main())
