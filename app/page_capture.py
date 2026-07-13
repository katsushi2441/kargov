"""Capture long web pages as readable viewport-sized PNG segments via kargov CDP."""
from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path

import websockets

from . import chrome
from .recorder import page_ws


class CDPClient:
    def __init__(self, ws):
        self.ws = ws
        self.message_id = 0

    async def call(self, method: str, params: dict | None = None) -> dict:
        self.message_id += 1
        message_id = self.message_id
        await self.ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(await self.ws.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} failed: {message['error']}")
                return message.get("result") or {}


def safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-") or "page"


async def capture_pages(
    pages: list[tuple[str, str]],
    output_dir: Path,
    *,
    width: int = 1440,
    height: int = 900,
    overlap: int = 120,
    wait_seconds: float = 1.2,
    debug_port: int = 9234,
) -> list[Path]:
    """Capture each URL in viewport segments and return all written PNG paths."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    process = chrome.launch(debug_port, headless=True, window=f"{width},{height}")
    written: list[Path] = []
    try:
        ws_url = await page_ws(debug_port)
        async with websockets.connect(ws_url, max_size=None) as ws:
            cdp = CDPClient(ws)
            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            await cdp.call("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
            })
            for label, url in pages:
                await cdp.call("Page.navigate", {"url": url})
                await asyncio.sleep(3)
                await cdp.call("Runtime.evaluate", {
                    "expression": "document.fonts && document.fonts.ready",
                    "awaitPromise": True,
                })
                metrics = await cdp.call("Runtime.evaluate", {
                    "expression": "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)",
                    "returnByValue": True,
                })
                page_height = int(metrics["result"]["value"])
                step = max(1, height - overlap)
                offsets = list(range(0, max(1, page_height - height + 1), step))
                last = max(0, page_height - height)
                if not offsets or offsets[-1] != last:
                    offsets.append(last)
                # Keep order while removing a duplicate final offset.
                offsets = list(dict.fromkeys(offsets))
                prefix = safe_name(label)
                for index, offset in enumerate(offsets, start=1):
                    await cdp.call("Runtime.evaluate", {
                        "expression": f"window.scrollTo(0,{offset}); new Promise(r=>setTimeout(r,{int(wait_seconds * 1000)}))",
                        "awaitPromise": True,
                    })
                    shot = await cdp.call("Page.captureScreenshot", {
                        "format": "png", "fromSurface": True, "captureBeyondViewport": False,
                    })
                    path = output_dir / f"{prefix}_{index:02d}.png"
                    path.write_bytes(base64.b64decode(shot["data"]))
                    written.append(path)
                (output_dir / f"{prefix}_capture.json").write_text(json.dumps({
                    "url": url,
                    "viewport": {"width": width, "height": height},
                    "page_height": page_height,
                    "overlap": overlap,
                    "segments": [p.name for p in written if p.name.startswith(prefix + "_") and p.suffix == ".png"],
                }, ensure_ascii=False, indent=2), encoding="utf-8")
        return written
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except Exception:
            process.kill()
