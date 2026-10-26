"""Atomic, live-checked local runtime state. Never trust a saved running flag."""
from datetime import datetime, timezone
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import sys
import time
import uuid


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def open_status_reader(path):
    """Open one status snapshot while allowing the writer to replace its path."""
    if sys.platform != "win32":
        return Path(path).open("r", encoding="utf-8-sig")
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    # FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE. The delete share
    # also permits rename/replace while this reader retains its old snapshot:
    # https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
    handle = kernel.CreateFileW(str(Path(path)), 0x80000000, 7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY | os.O_NOINHERIT)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    # Ownership transfers to the descriptor, then to the returned file object.
    try:
        return os.fdopen(descriptor, "r", encoding="utf-8-sig")
    except BaseException:
        os.close(descriptor)
        raise


def read_json(path):
    for attempt in range(3):
        try:
            with open_status_reader(path) as reader:
                value = json.load(reader)
            return value if isinstance(value, dict) else {}
        except PermissionError:
            if attempt < 2:
                time.sleep(.01)
        except (OSError, ValueError):
            return {}
    return {}


def _replace_status_file(temporary, path):
    if sys.platform != "win32":
        os.replace(temporary, path)
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    kernel.SetFileInformationByHandle.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
    kernel.SetFileInformationByHandle.restype = W.BOOL

    class RenameInfo(ctypes.Structure):
        _fields_ = [("flags", W.DWORD), ("root", W.HANDLE), ("length", W.DWORD), ("name", W.WCHAR * 1)]

    name = str(path.absolute()).encode("utf-16-le")
    buffer = ctypes.create_string_buffer(ctypes.sizeof(RenameInfo) + len(name))
    info = RenameInfo.from_buffer(buffer)
    # REPLACE_IF_EXISTS | POSIX_SEMANTICS retains open old snapshots and keeps
    # the destination continuously present, without ignoring read-only access:
    # https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information
    info.flags, info.length = 3, len(name)
    ctypes.memmove(ctypes.addressof(buffer) + RenameInfo.name.offset, name, len(name))
    handle = kernel.CreateFileW(str(temporary), 0x10000, 7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    fallback = False
    try:
        if not kernel.SetFileInformationByHandle(handle, 22, buffer, len(buffer)):  # FileRenameInfoEx
            error = ctypes.get_last_error()
            if error in (1, 50, 87):  # Older filesystems may not implement this operation.
                fallback = True
            else:
                raise ctypes.WinError(error)
    finally:
        kernel.CloseHandle(handle)
    if fallback:
        os.replace(temporary, path)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        for attempt in range(3):
            try:
                _replace_status_file(temporary, path)
                return
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(.01)
    finally:
        temporary.unlink(missing_ok=True)


def process_identity(pid):
    """Use kernel creation time to reject a reused PID; no process enumeration."""
    if not isinstance(pid, int) or pid <= 0:
        return {"alive": False, "reason": "process_missing"}
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return {"alive": True, "created": None}
        except ProcessLookupError:
            return {"alive": False, "reason": "process_missing"}
        except PermissionError:
            return {"alive": None, "reason": "process_access_denied"}
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
    kernel.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        return {"alive": False if error == 87 else None,
                "reason": "process_missing" if error == 87 else "process_access_denied"}
    try:
        code = W.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return {"alive": None, "reason": "process_query_failed"}
        if code.value != 259:
            return {"alive": False, "reason": "process_exited", "exit_code": code.value}
        times = [W.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in times)):
            return {"alive": None, "reason": "process_query_failed"}
        created = str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        return {"alive": True, "created": created}
    finally:
        kernel.CloseHandle(handle)


def health(path, *, lookup=process_identity, now=None, max_age=15):
    state = read_json(path)
    if not state:
        return {"state": "unavailable", "running": False, "reason": "no_status"}
    identity = lookup(state.get("pid"))
    if identity.get("alive") is False:
        return {**state, "running": False, "visible": False, "native_visible": False,
                "state": "stopped" if state.get("state") != "failed" else "failed",
                "health_reason": identity.get("reason", "process_missing")}
    if identity.get("alive") is None:
        return {**state, "running": None, "state": "unknown", "health_reason": identity.get("reason")}
    if state.get("process_created") and identity.get("created") != state["process_created"]:
        return {**state, "running": False, "visible": False, "native_visible": False,
                "state": "stopped", "health_reason": "pid_reused"}
    if not state.get("running"):
        return {**state, "health_reason": "reported_stopped"}
    try:
        age = (time.time() if now is None else now) - datetime.fromisoformat(state["updated_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        age = None
    if age is None or age > max_age or age < -5:
        return {**state, "running": None, "state": "unresponsive", "health_reason": "heartbeat_unavailable" if age is None else "heartbeat_stale"}
    return {**state, "state": "running", "running": True, "health_reason": "live", "heartbeat_age_seconds": round(age, 2)}


class RuntimeSession:
    def __init__(self, path, version, run_id=None):
        self.path = Path(path)
        self.run_id = run_id or uuid.uuid4().hex
        self.version = version
        self.started_at = utc_now()
        self.created = process_identity(os.getpid()).get("created")
        self.error = None
        self.reason = None

    def write(self, state):
        value = {**state, "schema_version": 2, "run_id": self.run_id,
                 "version": self.version, "pid": os.getpid(), "process_created": self.created,
                 "started_at": self.started_at, "updated_at": utc_now(),
                 "state": "running" if state.get("running") else "failed" if self.error else "stopped",
                 "exit_reason": self.reason, "error_type": self.error}
        atomic_json(self.path, value)

    def fail(self, exception, reason="unhandled_exception"):
        self.error, self.reason = type(exception).__name__, reason

    def finish(self, reason=None):
        self.reason = self.reason or reason or "mainloop_returned"
        state = read_json(self.path)
        if state.get("run_id") not in (None, self.run_id):
            return
        self.write({**state, "running": False, "visible": False, "native_visible": False})


def finish_child(path, run_id, exit_code):
    state = read_json(path)
    if state.get("run_id") != run_id:
        return False
    failed = exit_code != 0 or state.get("state") == "failed"
    state.update(running=False, visible=False, native_visible=False,
                 state="failed" if failed else "stopped", exit_code=exit_code,
                 exit_reason=state.get("exit_reason") or ("unexpected_process_exit" if failed else "process_exited"),
                 updated_at=utc_now(), supervisor_observed_exit=True)
    atomic_json(path, state)
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("status_file", type=Path)
    args = parser.parse_args()
    print(json.dumps(health(args.status_file), ensure_ascii=False, indent=2))
