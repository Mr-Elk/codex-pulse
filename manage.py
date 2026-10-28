"""Portable beta install/upgrade/rollback; independent of a developer checkout."""
import argparse
import ctypes
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

import release_tools
from runtime_state import atomic_json, health, read_json

BASE = Path(__file__).resolve().parent
RECOVERY_VERSION = "0.7.0-beta.6"
RECOVERY_SHA256 = "0bb7da9b8db9c6f045b9135350d4cc3a01fa6786810acf33c6a8951f61abb077"
BLOCKED_ROLLBACK_VERSIONS = {"0.7.0-beta.5"}


def installation(root):
    root = Path(root).resolve()
    marker = root / "installation.json"
    value = read_json(marker)
    if root.exists() and any(root.iterdir()) and value.get("name") != "codex-pulse-beta":
        raise ValueError("Choose an empty folder or an existing Codex Pulse beta installation")
    return root, marker, value


def version_dir(root, version):
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Invalid package version")
    return root / "versions" / version


def verify_version(root, version):
    folder = version_dir(root, version)
    manifest = read_json(folder / "release-manifest.json")
    if manifest.get("version") != version:
        raise ValueError("Installed version manifest is unavailable")
    for name, expected in manifest["files"].items():
        file = release_tools.inside(folder, name)
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError("Installed file changed; preserve edits before continuing: " + name)
    return folder


def stop(root, timeout=8):
    status = root / "data" / "runtime.json"
    deadline = time.monotonic() + timeout
    current = health(status)
    if current.get("running") is False:
        return
    if current.get("running") is not True:
        raise ValueError("Process identity/heartbeat cannot be verified; nothing was stopped")
    if sys.platform != "win32":
        raise ValueError("Stopping the overlay requires Windows")
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.IsWindow.argtypes = [W.HWND]
    user.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
    user.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    # A fresh launch can publish its process identity before Tk creates HWNDs.
    run_id=current.get("run_id")
    while not current.get("overlay_hwnd") and time.monotonic()<deadline:
        time.sleep(.05)
        current=health(status)
        if current.get("running") is False:return
        if current.get("run_id")!=run_id:raise ValueError("Runtime identity changed during startup; nothing was stopped")
    hwnd, pid = current.get("overlay_hwnd"), W.DWORD()
    if not hwnd or not user.IsWindow(hwnd):
        raise ValueError("Overlay window identity is unavailable; nothing was stopped")
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value != current.get("pid"):
        raise ValueError("Window/PID identity changed; nothing was stopped")
    user.PostMessageW(hwnd, 0x10, 0, 0)
    while time.monotonic() < deadline:
        check = health(status)
        # A reported normal close alone is not enough: wait for kernel exit.
        from runtime_state import process_identity
        if process_identity(current["pid"]).get("alive") is False:
            return
        time.sleep(.1)
    raise ValueError("Overlay did not exit; upgrade/rollback was not started")


def install(archive, root, recovery_archive=None):
    manifest = release_tools.verify_archive(archive)
    root, marker, previous = installation(root)
    folder = version_dir(root, manifest["version"])
    recovery = None
    if recovery_archive is not None:
        recovery_archive = Path(recovery_archive)
        recovery = release_tools.verify_archive(recovery_archive)
        if (recovery.get("version") != RECOVERY_VERSION or
                hashlib.sha256(recovery_archive.read_bytes()).hexdigest() != RECOVERY_SHA256):
            raise ValueError("Recovery archive is not the verified beta.6 baseline; installation was preserved")
        if recovery["version"] == manifest["version"]:
            raise ValueError("Recovery baseline must differ from the new candidate")
    # Validate every existing version before stopping the running candidate.
    if previous.get("current"):
        verify_version(root, previous["current"])
    if folder.exists():
        verify_version(root, manifest["version"])
        existing = read_json(folder / "release-manifest.json")
        if existing["files"] != manifest["files"]:
            raise ValueError("This version already exists with different package contents")
    if recovery is not None:
        recovery_folder = version_dir(root, recovery["version"])
        if recovery_folder.exists():
            verify_version(root, recovery["version"])
            if read_json(recovery_folder / "release-manifest.json")["files"] != recovery["files"]:
                raise ValueError("Existing recovery version differs; preserve its edits before installing")
    if previous.get("current"):
        stop(root)
    if recovery is not None and not recovery_folder.exists():
        release_tools.install_archive(recovery_archive, recovery_folder, root / "backups")
        atomic_json(recovery_folder / "release-manifest.json", recovery)
    if not folder.exists():
        release_tools.install_archive(archive, folder, root / "backups")
        atomic_json(folder / "release-manifest.json", manifest)
    root.mkdir(parents=True, exist_ok=True)
    controller = root / "controller"
    controller.mkdir(exist_ok=True)
    # Versioned controller backup is outside caches and is never deleted.
    backup = root / "backups" / ("controller-" + uuid.uuid4().hex)
    backup.mkdir(parents=True)
    for name in ("manage.py", "release_tools.py", "release_policy.py", "product_version.py", "runtime_state.py"):
        target = controller / name
        if target.exists():
            shutil.copy2(target, backup / name)
        shutil.copy2(BASE / name, target)
    previous_version = recovery["version"] if recovery is not None else (
        previous.get("current") if previous.get("current") != manifest["version"] else previous.get("previous"))
    if previous_version in BLOCKED_ROLLBACK_VERSIONS:
        previous_version = None
    value = {"name": "codex-pulse-beta", "current": manifest["version"],
             "previous": previous_version,
             "python": sys.executable}
    if recovery is not None:
        value["recovery_baseline"] = recovery["version"]
    # Publish the active pointer last. All preceding writes are recoverable.
    atomic_json(marker, value)
    for name, action in (("启动统计条.cmd", "launch"), ("回退上一版.cmd", "rollback"), ("检查运行状态.cmd", "status")):
        pause = "\r\npause" if action != "launch" else ""
        text = '@echo off\r\nchcp 65001 >nul\r\n"' + sys.executable + '" -X utf8 -B "%~dp0controller\\manage.py" ' + action + ' --target "%~dp0."' + pause + '\r\n'
        if action=="launch":
            text='@echo off\r\npowershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0start.ps1"\r\n'
        (root / name).write_text(text, encoding="utf-8")
    pythonw=Path(sys.executable).with_name("pythonw.exe")
    python=str(pythonw if pythonw.exists() else Path(sys.executable)).replace("'","''")
    start="$pulsePython = '"+python+"'\n$pulseArgs = @('-X','utf8','-B',('`\"' + (Join-Path $PSScriptRoot 'controller\\manage.py') + '`\"'),'launch','--target',('`\"' + $PSScriptRoot + '`\"'))\nStart-Process -WindowStyle Hidden -FilePath $pulsePython -ArgumentList $pulseArgs\n"
    # Single-quoted PowerShell strings need literal double quotes, no backticks.
    (root/"start.ps1").write_text(start.replace('`"','"'),encoding="utf-8-sig")
    return {"version": value["current"], "previous": value["previous"], "root": str(root)}


def rollback(root, dry_run=False):
    root, marker, current = installation(root)
    if not current.get("previous"):
        raise ValueError("No previous beta version; current installation was preserved")
    if current["previous"] in BLOCKED_ROLLBACK_VERSIONS:
        raise ValueError("Previous beta.5 has a known Escape-exit defect; use the installer with verified beta.6 recovery. Current installation was preserved")
    verify_version(root, current["current"])
    verify_version(root, current["previous"])
    if not dry_run:
        stop(root)
        current["current"], current["previous"] = current["previous"], current["current"]
        atomic_json(marker, current)
    return {"current": current["current"], "previous": current["previous"], "dry_run": dry_run}


def launch(root, extra=()):
    root, _, current = installation(root)
    folder = verify_version(root, current.get("current"))
    entry = folder / "launch.py" if (folder / "launch.py").exists() else folder / "overlay.py"
    command = [current["python"], "-X", "utf8", "-B", str(entry),
               "--settings-file", str(root / "data" / "settings.json"),
               "--status-file", str(root / "data" / "runtime.json"), *extra]
    return subprocess.call(command,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "launch", "rollback", "status", "stop"))
    parser.add_argument("archive", nargs="?", type=Path)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recovery-archive", type=Path)
    args, extra = parser.parse_known_args()
    if args.recovery_archive is not None and args.action != "install":
        parser.error("--recovery-archive is only valid for install")
    if extra and args.action != "launch":
        parser.error("Unknown arguments")
    if args.action == "launch":
        return launch(args.target, extra)
    if args.action == "install":
        if args.archive is None:
            parser.error("install requires an archive")
        result = install(args.archive, args.target, recovery_archive=args.recovery_archive)
    elif args.action == "rollback":
        result = rollback(args.target, args.dry_run)
    elif args.action == "stop":
        root, _, _ = installation(args.target)
        stop(root)
        result = {"stopped": True}
    else:
        root, _, _ = installation(args.target)
        result = health(root / "data" / "runtime.json")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
