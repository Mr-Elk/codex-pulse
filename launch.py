"""Hidden local supervisor: records child startup, exit code and stale status."""
import argparse
import ctypes
from ctypes import wintypes as W
import json
from logging.handlers import RotatingFileHandler
import logging
from pathlib import Path
import subprocess
import sys
import uuid

import overlay_settings as preferences
from runtime_state import atomic_json, finish_child, health, utc_now

BASE = Path(__file__).resolve().parent


def supervise(command, status, *, run_id, log_dir, version):
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("pulse-launch-" + run_id)
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_dir / "lifecycle.jsonl", maxBytes=262144, backupCount=2, encoding="utf-8")
    logger.addHandler(handler)
    logger.propagate = False
    def event(name, **values):
        logger.info(json.dumps({"at": utc_now(), "event": name, "run_id": run_id, "version": version, **values}))
    # Keep raw stderr local and bounded between launches; it never enters a ZIP.
    error_path = log_dir / "last-stderr.log"
    try:
        atomic_json(status, {"schema_version": 2, "run_id": run_id, "version": version,
                            "pid": None, "running": False, "state": "starting", "updated_at": utc_now()})
        with error_path.open("w", encoding="utf-8") as error_log:
            child = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=error_log,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            event("started", child_pid=child.pid)
            code = child.wait()
        finish_child(status, run_id, code)
        event("exited", child_pid=child.pid, exit_code=code)
        return code
    except Exception as exception:
        finish_child(status, run_id, 1)
        event("launcher_failed", error_type=type(exception).__name__)
        raise
    finally:
        handler.close()
        logger.removeHandler(handler)


def main():
    if sys.platform != "win32":
        raise SystemExit("Codex Pulse requires Windows")
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,W.BOOL,W.LPCWSTR]
    kernel.CreateMutexW.restype=W.HANDLE
    kernel.CloseHandle.argtypes=[W.HANDLE]
    mutex=kernel.CreateMutexW(None,False,"Local\\CodexPulseLaunchSupervisor")
    if not mutex:raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error()==183:
        kernel.CloseHandle(mutex)
        print("Codex Pulse supervisor is already running.")
        return 0
    try:
        return launch_main()
    finally:
        kernel.CloseHandle(mutex)


def launch_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings-file", type=Path, default=preferences.default_path())
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--log-dir", type=Path)
    args, extra = parser.parse_known_args()
    status = args.status_file or args.settings_file.with_name("runtime.json")
    live = health(status)
    if live.get("running") is True or live.get("state") in ("unknown", "unresponsive"):
        print("Codex Pulse already has a live or unverifiable process; close/check it before starting another.")
        return 0
    run_id = uuid.uuid4().hex
    version = json.loads((BASE / "plugin.json").read_text(encoding="utf-8"))["version"]
    command = [sys.executable, "-X", "utf8", "-B", str(BASE / "overlay.py"),
               "--settings-file", str(args.settings_file), "--status-file", str(status), "--run-id", run_id, *extra]
    return supervise(command, status, run_id=run_id,
                     log_dir=args.log_dir or status.parent / "logs", version=version)


if __name__ == "__main__":
    sys.exit(main())
