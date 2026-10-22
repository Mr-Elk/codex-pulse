"""A persistent, read-only Windows UIA helper, separate from metric collection."""
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

from overlay_geometry import Rect


def parse_context(value):
    if not isinstance(value, dict):
        return None, None, "unavailable", None
    composer = value.get("composer")
    if value.get("composer_source") not in (None,"named"):
        composer = None
    rect = None
    if isinstance(composer, dict) and set(composer) == {"left", "top", "right", "bottom"}:
        if all(type(number) is int for number in composer.values()):
            candidate = Rect(**composer)
            if candidate.width > 0 and candidate.height > 0:
                rect = candidate
    interaction = value.get("interaction_open")
    return rect, value.get("chat_title"), value.get("chat_status", "unavailable"), interaction if type(interaction) is bool else None


class PersistentProbe:
    def __init__(self, script=None, command_factory=None):
        self.script = script or Path(__file__).with_name("composer_anchor.ps1")
        self.command_factory = command_factory
        self.process = None
        self.hwnd = None
        self.responses = queue.Queue()
        self.inflight = False
        self.starts = 0
        self.requests = 0
        self.last_latency_ms = None
        self.response_at = 0
        self.started_at = 0
        self.avoid_rect = None

    @staticmethod
    def _read(process, responses):
        try:
            for line in process.stdout:
                try:
                    value = json.loads(line.strip().lstrip("\ufeff"))
                except ValueError:
                    value = None
                responses.put(value)
        except (OSError, ValueError):
            pass
        finally:
            responses.put(None)

    def start(self, hwnd):
        self.close()
        command = self.command_factory(hwnd) if self.command_factory else [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(self.script),
            "-WindowHandle", str(hwnd), "-IncludeChat", "-Watch"]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                        bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.hwnd = hwnd
        self.responses = queue.Queue()
        threading.Thread(target=self._read, args=(self.process, self.responses), daemon=True).start()
        self.starts += 1

    def read(self, hwnd, timeout=4):
        if self.process is None or self.hwnd != hwnd or self.process.poll() is not None:
            self.start(hwnd)
        if not self.inflight:
            self.process.stdin.write("probe\n")
            self.process.stdin.flush()
            self.inflight = True
            self.started_at = time.monotonic()
            self.requests += 1
        try:
            value = self.responses.get(timeout=timeout)
        except queue.Empty:
            # Keep waiting for this same request and process on the next call.
            # Observation timeout alone does not trigger duplicate probes.
            return None, None, "unavailable", None
        self.inflight = False
        self.response_at = time.monotonic()
        self.last_latency_ms = round((self.response_at - self.started_at) * 1000, 1)
        self.avoid_rect = None
        if isinstance(value,dict):
            rect,_,_,_ = parse_context({"composer":value.get("popup_bounds")})
            self.avoid_rect = rect
        return parse_context(value)

    def close(self):
        process, self.process = self.process, None
        self.inflight = False
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()  # EOF lets an idle helper exit normally.
            if process.poll() is None:
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.terminate()  # Our helper only, during explicit shutdown.
                    process.wait(timeout=2)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        finally:
            if process.stdout:
                process.stdout.close()
