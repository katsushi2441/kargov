"""Chrome (remote debugging) 起動 と Cookie注入 (A3)。"""
import asyncio, json, subprocess, time, urllib.request
from pathlib import Path
import websockets

from . import config


def launch(debug_port: int, headless: bool = True, window: str = None) -> subprocess.Popen:
    subprocess.run(["pkill", "-f", f"remote-debugging-port={debug_port}"], check=False)
    time.sleep(1)
    win = window or f"{config.REC_WIDTH},{config.REC_HEIGHT}"
    args = [
        config.CHROME_BIN,
        f"--remote-debugging-port={debug_port}", "--remote-debugging-address=127.0.0.1",
        "--no-sandbox", "--disable-gpu", f"--window-size={win}",
        "--no-first-run", "--no-default-browser-check",
    ]
    if headless:
        args.insert(1, "--headless=new")
    args.append("about:blank")
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def set_cookies(debug_port: int, cookies: list[dict]):
    """ログイン済みセッションのCookieをCDPで注入し、認証済み状態から操作開始 (A3)。

    cookies: [{"name","value","domain","path","secure","httpOnly","sameSite"}, ...]
    """
    from .recorder import page_ws
    ws_url = await page_ws(debug_port)
    async with websockets.connect(ws_url, max_size=None) as ws:
        mid = 0

        async def send(method, params=None):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            return await ws.recv()

        await send("Network.enable")
        for c in cookies:
            ck = {"path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax", **c}
            await send("Network.setCookie", ck)
