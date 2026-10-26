"""Read-only, current-thread Codex usage monitor. Python standard library only."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import datetime, timezone
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parent
FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, AttributeError, OverflowError, OSError):
        return None


def usage(value):
    if not isinstance(value, dict):
        return None
    if not all(isinstance(value.get(k), int) and not isinstance(value[k], bool) and value[k] >= 0 for k in FIELDS):
        return None
    return {k: value[k] for k in FIELDS}


def pair_requests(records, starts):
    """Only pair one start in the completion interval; retries remain unknown."""
    times = sorted(s["time"] for s in starts)
    by_time = {s["time"]: s for s in starts}
    result = []
    previous = float("-inf")
    for record in sorted(records, key=lambda r: r["time"]):
        lo, hi = bisect_right(times, previous), bisect_right(times, record["time"])
        candidates = [by_time[t] for t in times[lo:hi]
                      if not record.get("turn_id") or by_time[t].get("turn_id") == record["turn_id"]]
        duration = record["time"] - candidates[0]["time"] if len(candidates) == 1 else None
        if duration is not None and not 0.05 <= duration <= 3600:
            duration = None
        result.append({**record, "duration_seconds": duration,
                       "tps": record["usage"]["output_tokens"] / duration if duration else None})
        previous = record["time"]
    return result


class Monitor:
    def __init__(self, codex_home, thread_id, session_file=None):
        self.home = Path(codex_home)
        self.thread_id = thread_id
        self.path = Path(session_file) if session_file else None
        self.offset = 0
        self.identity = None
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.records = []
        self.legacy = []
        self.seen = set()
        self.turns = {}
        self.current_turn = None
        self.model = None
        self.context_window = None
        self.total = None
        self.last_usage = None
        self.legacy_total = None
        self.starts = []
        self.last_log_id = 0
        self.log_identity = None
        self.start_keys = set()
        self.log_issue = False
        self.last_record_at = None
        self.metrics_issue = False

    def locate(self):
        if self.path is None:
            # Explicit thread selection: never silently switch to the newest chat.
            matches = list((self.home / "sessions").glob(f"**/*{self.thread_id}*.jsonl"))
            if len(matches) == 1:
                self.path = matches[0]

    def consume(self, row):
        kind, payload = row.get("type"), row.get("payload", {})
        if not isinstance(payload, dict):
            return
        if kind == "event_msg":
            kind = payload.get("type")
        at = timestamp(row.get("timestamp"))
        if kind == "session_meta":
            if payload.get("id") != self.thread_id:
                raise ValueError("Session file does not match the selected thread.")
        elif kind in ("task_started", "turn_started"):
            turn_id = payload.get("turn_id")
            if turn_id is not None and not isinstance(turn_id, str):
                self.metrics_issue = True
                return
            if turn_id:
                self.current_turn = turn_id
                self.turns.setdefault(turn_id, {"start": timestamp(payload.get("started_at")) or at, "end": None})
            self.read_context_window(payload)
        elif kind in ("task_complete", "turn_complete", "turn_aborted", "task_aborted"):
            turn_id = payload.get("turn_id") or self.current_turn
            if turn_id is not None and not isinstance(turn_id, str):
                self.metrics_issue = True
                return
            if turn_id in self.turns:
                self.turns[turn_id]["end"] = at
        elif kind == "turn_context":
            self.model = payload.get("model") or self.model
        elif kind == "token_usage_record":
            if payload.get("thread_id") != self.thread_id or at is None:
                return
            key = payload.get("response_id")
            turn_id = payload.get("turn_id")
            if not isinstance(key, str) or (turn_id is not None and not isinstance(turn_id, str)):
                self.metrics_issue = True
                return
            current = usage(payload.get("usage"))
            total = usage(payload.get("thread_token_usage"))
            if not key or key in self.seen:
                return
            if current is None or total is None:
                self.metrics_issue = True
                return
            self.seen.add(key)
            self.records.append({"time": at, "turn_id": payload.get("turn_id"), "usage": current})
            self.total, self.last_usage, self.last_record_at = total, current, at
        elif kind == "token_count":
            info = payload.get("info")
            if info is None:
                return
            if not isinstance(info, dict):
                self.metrics_issue = True
                return
            self.read_context_window(info)
            total, current = usage(info.get("total_token_usage")), usage(info.get("last_token_usage"))
            if total and current and at and total != self.legacy_total:
                self.legacy.append({"time": at, "turn_id": self.current_turn, "usage": current})
                self.legacy_total = total
                if not self.records:
                    self.total, self.last_usage, self.last_record_at = total, current, at

    def read_context_window(self, payload):
        value = payload.get("model_context_window")
        if value is None:
            return
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            self.context_window = value
        else:
            self.context_window = None
            self.metrics_issue = True

    def read_session(self):
        self.locate()
        if self.path is None:
            return
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if self.identity is not None and (identity != self.identity or stat.st_size < self.offset):
            self.offset = 0
            self.reset()
        self.identity = identity
        with self.path.open("rb") as source:
            source.seek(self.offset)
            while True:
                line = source.readline()
                if not line or not line.endswith(b"\n"):
                    break  # Re-read a partial trailing record on the next refresh.
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    self.metrics_issue = True
                    self.offset = source.tell()
                    continue
                if isinstance(row, dict):
                    self.consume(row)
                self.offset = source.tell()

    def read_starts(self):
        path = self.home / "logs_2.sqlite"
        try:
            stat = path.stat()
            identity = (stat.st_dev, stat.st_ino)
            cursor = self.last_log_id if identity == self.log_identity else 0
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.15)) as conn:
                conn.execute("PRAGMA query_only=ON")
                maximum = conn.execute("SELECT MAX(id) FROM logs").fetchone()[0]
                if maximum is not None and maximum < cursor:
                    cursor = 0  # Table reset can preserve the database inode.
                rows = conn.execute(
                    "SELECT id, ts, ts_nanos, feedback_log_body FROM logs "
                    "WHERE id > ? AND thread_id = ? AND target = 'feedback_tags' "
                    "AND feedback_log_body LIKE '%stream_request{%' ORDER BY id",
                    (cursor, self.thread_id)).fetchall()
            self.last_log_id, self.log_identity = cursor, identity
            for log_id, seconds, nanos, body in rows:
                self.last_log_id = log_id
                if "websocket.warmup=true" in body:
                    continue
                match = re.search(r'\bturn_id="?([a-zA-Z0-9-]+)', body)
                turn_id = match.group(1) if match else None
                key = (log_id, seconds, nanos, turn_id)
                if key not in self.start_keys:
                    self.start_keys.add(key)
                    self.starts.append({"time": seconds + nanos / 1e9, "turn_id": turn_id})
            self.log_issue = False
        except (sqlite3.Error, OSError, ValueError):
            self.log_issue = True

    def request_pending(self):
        if not self.starts:
            return False
        latest=self.starts[-1]
        if self.last_record_at is not None and latest["time"]<=self.last_record_at:
            return False
        turn=self.turns.get(latest.get("turn_id") or self.current_turn,{})
        ended=turn.get("end")
        return ended is None or ended<latest["time"]

    def snapshot(self, now=None):
        with self.lock:
            now = time.time() if now is None else now
            try:
                self.read_session()
                self.read_starts()
            except OSError:
                return {"available": False, "reason": "暂时无法读取当前对话记录。"}
            except ValueError:
                return {"available": False, "reason": "记录文件与当前对话不匹配，已停止读取。"}
            if not self.total:
                return {"available": False, "request_pending":self.request_pending(),
                        "reason": "当前对话尚无用量记录，或该版本使用了不同的记录格式。"}
            records = pair_requests(self.records or self.legacy, self.starts)
            turn = self.turns.get(self.current_turn, {})
            current = [r for r in records if r.get("turn_id") == self.current_turn]
            latest = records[-1] if records else None
            elapsed = max(0, (turn.get("end") or now) - turn["start"]) if turn.get("start") else None
            turn_output = sum(r["usage"]["output_tokens"] for r in current)
            last = self.last_usage
            cached = last["cached_input_tokens"] / last["input_tokens"] * 100 if last["input_tokens"] else None
            context = (last["input_tokens"] + last["output_tokens"]) / self.context_window * 100 if self.context_window else None
            pending = self.request_pending()
            warnings = []
            if self.log_issue:
                warnings.append("请求计时日志暂不可用；TPS 留空。")
            if self.metrics_issue:
                warnings.append("部分用量记录无法解析，统计可能不完整。")
            return {
                "available": True, "thread_id": self.thread_id, "model": self.model,
                "updated_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "last_usage_at": datetime.fromtimestamp(self.last_record_at, timezone.utc).isoformat(),
                "state": "complete" if turn.get("end") else "in_progress" if turn else "unknown",
                "request_pending": pending, "rounds": len(self.turns), "requests": len(records),
                "turn_requests": len(current), "latest_tps_estimate": latest["tps"] if latest and not self.log_issue else None,
                "latest_request_seconds_estimate": latest["duration_seconds"] if latest and not self.log_issue else None,
                "turn_average_tps": turn_output / elapsed if elapsed else None,
                "turn_elapsed_seconds": elapsed, "turn_output_tokens": turn_output,
                "usage": self.total, "last_usage": last, "cache_hit_percent": cached,
                "context_percent_estimate": context, "context_window": self.context_window,
                "history": [{"at": r["time"], "tps": r["tps"], "output_tokens": r["usage"]["output_tokens"]} for r in records[-24:]],
                "source": "token_usage_record" if self.records else "token_count", "warnings": warnings,
            }


def make_handler(monitor):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # No CORS. Reject cross-origin browser requests and foreign Host headers.
            host = self.headers.get("Host", "")
            if host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
                self.send_error(403)
                return
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send_error(403)
                return
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"):
                self.send_error(403)
                return
            route = urlsplit(self.path).path
            if route == "/api/snapshot":
                try:
                    body = json.dumps(monitor.snapshot(), ensure_ascii=False).encode("utf-8")
                except Exception:
                    self.send_error(500, "Local metrics unavailable")
                    return
                kind = "application/json; charset=utf-8"
            elif route in ("/", "/index.html"):
                body = (BASE / "index.html").read_bytes()
                kind = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID"))
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--session-file", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not args.thread_id or not re.fullmatch(r"[0-9a-fA-F-]{36}", args.thread_id):
        parser.error("Provide the current Codex thread UUID with --thread-id.")
    monitor = Monitor(args.codex_home.resolve(), args.thread_id, args.session_file)
    if args.once:
        print(json.dumps(monitor.snapshot(), ensure_ascii=False, indent=2))
        return
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(monitor))
    print(f"Codex Pulse http://127.0.0.1:{server.server_port} | current thread {args.thread_id}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
