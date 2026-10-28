"""Bounded Windows CI checks with durable logs and the original failure status."""
from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run_logged(command, log_path, *, cwd, timeout):
    """Keep stdout and stderr even when a child fails, cannot start, or times out."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        try:
            result = subprocess.run(
                command, cwd=cwd, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, timeout=timeout,
            )
            code = result.returncode
        except subprocess.TimeoutExpired:
            log.write(f"\nCI check timed out after {timeout} seconds.\n")
            code = 124
        except OSError as error:
            log.write(f"\nCI check could not start: {type(error).__name__}: {error}\n")
            code = 127
    print(log_path.read_text(encoding="utf-8", errors="replace"), end="", flush=True)
    print(f"CI check exit code: {code}; log: {log_path.name}", flush=True)
    return code


def preflight():
    if os.name != "nt":
        raise RuntimeError("The full desktop regression requires Windows.")
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or newer is required.")
    print(f"Python: {sys.version.split()[0]}", flush=True)
    for library in ("user32", "gdiplus"):
        ctypes.WinDLL(library)
        print(f"{library}: available", flush=True)

    import tkinter as tk

    root = tk.Tk()
    try:
        root.withdraw()
        root.update_idletasks()
        print(f"Tk window: created; Tcl/Tk {root.tk.call('info', 'patchlevel')}", flush=True)
    finally:
        root.destroy()

    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise RuntimeError("Windows PowerShell is required.")
    subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command",
         "[Console]::WriteLine($PSVersionTable.PSVersion.ToString())"],
        check=True, timeout=15,
    )
    print("Windows PowerShell: available", flush=True)


def run_ci(log_dir):
    log_dir = Path(log_dir).resolve()
    code = run_logged(
        [sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()), "--preflight"],
        log_dir / "preflight.log", cwd=ROOT, timeout=45,
    )
    if code:
        return code
    return run_logged(
        [sys.executable, "-X", "utf8", "-B", "-m", "unittest", "discover", "-v"],
        log_dir / "unittest.log", cwd=ROOT, timeout=900,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, default=Path("ci-logs"))
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args(argv)
    if args.preflight:
        preflight()
        return 0
    return run_ci(args.log_dir)


if __name__ == "__main__":
    raise SystemExit(main())
