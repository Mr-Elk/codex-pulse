"""A persistent, read-only Windows UIA helper, separate from metric collection."""
import json
import os
from pathlib import Path
import queue
import re
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


def context_metadata(value):
    """Only the navigation title and named-composer evidence classify a page."""
    if not isinstance(value, dict):
        return {"page_kind": "unknown", "composer_status": "unavailable"}
    composer, title, status, _ = parse_context(value)
    non_work = status == "ok" and isinstance(title, str) and re.fullmatch(
        r"(?:个人资料|个人主页|设置|归档|Profile|Settings|Archived)(?:\s*[-–—|·]\s*(?:ChatGPT|Codex))?", title.strip(), re.I)
    return {"page_kind": "non_work" if non_work else "work" if composer is not None else "unknown",
            "composer_status": "found" if composer is not None else
            "absent" if value.get("composer_status") == "absent" else "unavailable"}


class PersistentProbe:
    def __init__(self, script=None, command_factory=None, *, max_requests=256,
                 max_age=300, max_private_mib=160, request_deadline=15, clock=time.monotonic):
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
        self.ignored_own_elements = 0
        self.metadata = context_metadata(None)
        self.clock = clock
        self.max_requests = max_requests
        self.max_age = max_age
        self.max_private_mib = max_private_mib
        self.request_deadline = request_deadline
        self.process_started_at = 0
        self.completed = 0
        self.private_bytes = 0
        self.recycles = 0
        self.last_recycle_reason = None

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
            "-WindowHandle", str(hwnd), "-IncludeChat", "-Watch", "-IgnoreProcessId", str(os.getpid()),
            "-MaxRequests", str(self.max_requests), "-MaxAgeSeconds", str(self.max_age),
            "-MaxPrivateMiB", str(self.max_private_mib)]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                        bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.hwnd = hwnd
        self.responses = queue.Queue()
        threading.Thread(target=self._read, args=(self.process, self.responses), daemon=True).start()
        self.starts += 1
        self.process_started_at = self.clock()
        self.completed = 0
        self.private_bytes = 0

    def recycle_reason(self):
        if self.inflight:
            return "stalled" if self.started_at and self.clock() - self.started_at >= self.request_deadline else None
        if self.completed >= self.max_requests:
            return "requests"
        if self.clock() - self.process_started_at >= self.max_age:
            return "age"
        if self.private_bytes >= self.max_private_mib * 1024 * 1024:
            return "memory"
        return None

    def read(self, hwnd, timeout=4):
        reason = self.recycle_reason() if self.process is not None else None
        if reason:
            self.recycles += 1
            self.last_recycle_reason = reason
            self.close()
        if self.process is None or self.hwnd != hwnd or self.process.poll() is not None:
            self.start(hwnd)
        if not self.inflight:
            try:
                self.process.stdin.write("probe\n")
                self.process.stdin.flush()
            except (OSError, ValueError):
                # A helper can exit after delivering a valid bounded-lifetime
                # response, between poll() and write(). Retry only this request.
                self.start(hwnd)
                self.process.stdin.write("probe\n")
                self.process.stdin.flush()
            self.inflight = True
            self.started_at = self.clock()
            self.requests += 1
        try:
            value = self.responses.get(timeout=timeout)
        except queue.Empty:
            # Keep waiting for this same request and process on the next call.
            # Observation timeout alone does not trigger duplicate probes.
            self.metadata = context_metadata(None)
            return None, None, "unavailable", None
        self.inflight = False
        self.response_at = self.clock()
        self.completed += 1
        private = value.get("probe_private_bytes") if isinstance(value, dict) else None
        self.private_bytes = private if type(private) is int and private >= 0 else 0
        self.last_latency_ms = round((self.response_at - self.started_at) * 1000, 1)
        self.avoid_rect = None
        self.metadata = context_metadata(value)
        self.ignored_own_elements = value.get('ignored_own_elements',0) if isinstance(value,dict) and type(value.get('ignored_own_elements',0)) is int else 0
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
                    process.terminate()  # Only the child owned by this object.
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        finally:
            if process.stdout:
                process.stdout.close()
        if process.poll() is None:
            # Never create another helper while an owned one could still run.
            self.process = process
            raise OSError("Locator helper could not be stopped")
