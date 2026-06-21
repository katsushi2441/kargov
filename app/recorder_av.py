"""Audio/video recorder for real browser playback.

CDP Page.startScreencast is video-only.  This recorder follows the same path
used by the kvtuber YouTube Live flow: Xvfb for pixels, PulseAudio null-sink
for browser audio, and ffmpeg x11grab+pulse for a muxed raw.mp4.
"""
import json
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

from . import config


class AVRecorder:
    def __init__(
        self,
        debug_port: int,
        out_dir: Path,
        display: str | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
        sink_name: str | None = None,
        app_mode: bool = False,
    ):
        self.debug_port = debug_port
        self.out_dir = Path(out_dir)
        self.display = display or config.AV_DISPLAY
        self.width = width or config.REC_WIDTH
        self.height = height or config.REC_HEIGHT
        self.fps = fps or config.AV_FPS
        self.sink_name = sink_name or config.AV_PULSE_SINK
        self.app_mode = app_mode
        self.audio_source = f"{self.sink_name}.monitor"
        self.marks: list[dict] = []
        self._t0: float | None = None
        self.xvfb_proc: subprocess.Popen | None = None
        self.chrome_proc: subprocess.Popen | None = None
        self.ffmpeg_proc: subprocess.Popen | None = None
        self.raw_path: Path | None = None

    def _run(self, args: list[str], check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True, text=True, check=check)

    def _command_exists(self, command: str) -> bool:
        return subprocess.run(["bash", "-lc", f"command -v {command}"],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0

    def _kill_existing_xvfb(self):
        result = self._run(["ps", "-eo", "pid=,args="])
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            pid_s, _, args = line.partition(" ")
            if args.startswith(f"Xvfb {self.display} "):
                try:
                    os.kill(int(pid_s), signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def _kill_debug_chrome(self):
        subprocess.run(["pkill", "-f", f"remote-debugging-port={self.debug_port}"],
                       check=False)

    def _ensure_pulse_sink(self):
        if not self._command_exists("pactl"):
            raise RuntimeError("pactl is required for AV recording")
        subprocess.run(["pulseaudio", "--start"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sinks = self._run(["pactl", "list", "short", "sinks"]).stdout or ""
        if self.sink_name not in sinks:
            self._run([
                "pactl",
                "load-module",
                "module-null-sink",
                f"sink_name={self.sink_name}",
                f"sink_properties=device.description={self.sink_name}",
            ])
        self._run(["pactl", "set-default-sink", self.sink_name])

    def _wait_for_cdp(self):
        url = f"http://127.0.0.1:{self.debug_port}/json/version"
        last_error = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    json.loads(response.read())
                    return
            except Exception as error:
                last_error = error
                time.sleep(0.25)
        raise RuntimeError(f"Chrome CDP did not become ready: {last_error}")

    def mark(self, name: str):
        if self._t0 is None:
            self.marks.append({"name": name, "t": 0.0})
        else:
            self.marks.append({"name": name, "t": time.time() - self._t0})

    @property
    def duration(self) -> float:
        if self._t0 is None:
            return 0.0
        return time.time() - self._t0

    @property
    def frame_times(self) -> list[float]:
        return []

    def start(self, url: str = "about:blank") -> subprocess.Popen:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for command in ("Xvfb", config.CHROME_BIN, config.FFMPEG_BIN):
            if not self._command_exists(command):
                raise RuntimeError(f"{command} is required for AV recording")

        self._ensure_pulse_sink()
        self._kill_existing_xvfb()
        self._kill_debug_chrome()
        time.sleep(0.5)

        geometry = f"{self.width}x{self.height}x24"
        self.xvfb_proc = subprocess.Popen(
            ["Xvfb", self.display, "-screen", "0", geometry, "-ac"],
            stdout=(self.out_dir / "xvfb.log").open("a"),
            stderr=(self.out_dir / "xvfb.err.log").open("a"),
        )
        time.sleep(1.0)

        profile_dir = self.out_dir / "chrome-profile"
        chrome_args = [
            config.CHROME_BIN,
            f"--remote-debugging-port={self.debug_port}",
            "--remote-debugging-address=127.0.0.1",
            "--remote-allow-origins=*",
            "--no-sandbox",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-session-crashed-bubble",
            "--disable-features=Translate,MediaRouter",
            "--autoplay-policy=no-user-gesture-required",
            "--disable-infobars",
            "--simulate-outdated-no-au=Tue, 31 Dec 2099 23:59:59 GMT",
            f"--user-data-dir={profile_dir}",
            "--window-position=0,0",
            f"--window-size={self.width},{self.height}",
        ]
        target_url = url or "about:blank"
        if self.app_mode and target_url.startswith(("http://", "https://")):
            # App mode removes Chrome UI/update prompts from the captured pixels.
            chrome_args.append(f"--app={target_url}")
        else:
            chrome_args.append(target_url)
        env = {**os.environ, "DISPLAY": self.display, "PULSE_SINK": self.sink_name}
        self.chrome_proc = subprocess.Popen(
            chrome_args,
            env=env,
            stdout=(self.out_dir / "chrome.log").open("a"),
            stderr=(self.out_dir / "chrome.err.log").open("a"),
        )
        self._wait_for_cdp()

        self.raw_path = self.out_dir / "raw.mp4"
        ffmpeg_args = [
            config.FFMPEG_BIN,
            "-y",
            "-f",
            "x11grab",
            "-thread_queue_size",
            "1024",
            "-video_size",
            f"{self.width}x{self.height}",
            "-framerate",
            str(self.fps),
            "-i",
            f"{self.display}.0",
            "-f",
            "pulse",
            "-thread_queue_size",
            "1024",
            "-i",
            self.audio_source,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(self.raw_path),
        ]
        self.ffmpeg_proc = subprocess.Popen(
            ffmpeg_args,
            env={**os.environ, "DISPLAY": self.display},
            stdout=(self.out_dir / "ffmpeg.log").open("a"),
            stderr=(self.out_dir / "ffmpeg.err.log").open("a"),
        )
        self._t0 = time.time()
        return self.chrome_proc

    async def stop_and_encode(self, mp4_path: Path) -> Path:
        if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            self.ffmpeg_proc.terminate()
            try:
                self.ffmpeg_proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.ffmpeg_proc.kill()
                self.ffmpeg_proc.wait(timeout=3)
        raw_path = self.raw_path or self.out_dir / "raw.mp4"
        if not raw_path.exists():
            raise RuntimeError("AV raw recording was not created")
        mp4_path = Path(mp4_path)
        if raw_path.resolve() != mp4_path.resolve():
            mp4_path.write_bytes(raw_path.read_bytes())
        return mp4_path

    def close(self):
        for proc in (self.ffmpeg_proc, self.chrome_proc, self.xvfb_proc):
            if proc and proc.poll() is None:
                proc.terminate()
        for proc in (self.ffmpeg_proc, self.chrome_proc, self.xvfb_proc):
            if proc and proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
