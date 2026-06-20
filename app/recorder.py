"""CDP screencast レコーダ (browser_agent/cdp_record.py を母体に拡張)。

母体から残す強み:
- x11grab非依存、ブラウザ中身だけを録画 (A4)
- 可変フレーム間隔 → concat demuxer で実時間に忠実 (A6)

拡張:
- mark(name) でシーン境界の録画内時刻を記録 (B1: ナレーション整列の土台)
"""
import asyncio, base64, json, time, subprocess, urllib.request
from pathlib import Path
import websockets

from . import config


async def page_ws(debug_port: int) -> str:
    """最初の page ターゲットの ws URL を取得。"""
    for _ in range(30):
        try:
            data = json.loads(
                urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json", timeout=3).read()
            )
            pages = [t for t in data if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
            if pages:
                return pages[0]["webSocketDebuggerUrl"]
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError("page target not found")


class ScreencastRecorder:
    def __init__(self, debug_port: int, out_dir: Path):
        self.debug_port = debug_port
        self.out_dir = Path(out_dir)
        self.frames_dir = self.out_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self._stop = asyncio.Event()
        self._task = None
        self.frame_times = []        # 各フレームの録画開始からの秒数
        self.marks = []              # [{"name":..., "t":秒}] シーン境界 (B1)
        self._t0 = None

    # --- シーンマーク (B1) ---
    def mark(self, name: str):
        """現在時刻をシーン境界として記録。browser-useの各ステップ等から呼ぶ。"""
        if self._t0 is None:
            self.marks.append({"name": name, "t": 0.0})
        else:
            self.marks.append({"name": name, "t": time.time() - self._t0})

    async def _run(self):
        ws_url = await page_ws(self.debug_port)
        async with websockets.connect(ws_url, max_size=None) as ws:
            mid = 0

            async def send(method, params=None):
                nonlocal mid
                mid += 1
                await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))

            await send("Page.enable")
            await send("Page.startScreencast", {
                "format": "jpeg", "quality": config.SCREENCAST_QUALITY, "everyNthFrame": 1,
            })
            n = 0
            self._t0 = time.time()
            while not self._stop.is_set():
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(msg)
                if d.get("method") == "Page.screencastFrame":
                    p = d["params"]
                    (self.frames_dir / f"f{n:06d}.jpg").write_bytes(base64.b64decode(p["data"]))
                    self.frame_times.append(time.time() - self._t0)
                    n += 1
                    await send("Page.screencastFrameAck", {"sessionId": p["sessionId"]})
            await send("Page.stopScreencast")

    def start(self):
        self._task = asyncio.create_task(self._run())

    @property
    def duration(self) -> float:
        return self.frame_times[-1] if self.frame_times else 0.0

    async def stop_and_encode(self, mp4_path: Path) -> Path:
        self._stop.set()
        if self._task:
            await self._task
        frames = sorted(self.frames_dir.glob("f*.jpg"))
        if not frames:
            raise RuntimeError("no frames captured")
        lines = []
        for i, fr in enumerate(frames):
            lines.append(f"file '{fr.name}'")
            if i < len(frames) - 1:
                dur = max(0.02, self.frame_times[i + 1] - self.frame_times[i])
                lines.append(f"duration {dur:.3f}")
        (self.frames_dir / "list.txt").write_text("\n".join(lines) + "\n")
        subprocess.run([
            config.FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0",
            "-i", str(self.frames_dir / "list.txt"),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-vsync", "vfr", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(Path(mp4_path).resolve()),
        ], check=True, cwd=str(self.frames_dir),
           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return Path(mp4_path)
