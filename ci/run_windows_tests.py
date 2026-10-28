"""Bounded Windows CI checks with durable logs and the original failure status."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import re


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from release_policy import clean_revision


def candidate_identity():
    revision = clean_revision(ROOT)
    if sys.platform != "win32" or sys.maxsize <= 2**32 or revision is None:
        raise ValueError("Candidate regression requires clean source and 64-bit Windows Python")
    dll = ROOT / "assets/native/pulse_backdrop_x64.dll"
    return {"source_revision": revision, "dll_sha256": hashlib.sha256(dll.read_bytes()).hexdigest()}


def save_receipt(path, log, identity):
    raw = Path(log).read_bytes()
    text = raw.decode("utf-8-sig")
    counts = re.findall(r"(?m)^Ran ([1-9][0-9]*) tests? in [0-9.]+s\s*$", text)
    if len(counts) != 1 or text.strip().splitlines()[-1] != "OK":
        raise ValueError("Candidate regression cannot contain failures or skips")
    value = {"schema": 1, "platform": "windows-x64", "python": sys.version.split()[0],
             **identity, "count": int(counts[0]), "result": "OK",
             "log_sha256": hashlib.sha256(raw).hexdigest()}
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)


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


def run_ci(log_dir, *, candidate_receipt=False):
    log_dir = Path(log_dir).resolve()
    if candidate_receipt:
        if (log_dir / "regression.json").exists():
            raise FileExistsError("Candidate regression receipt already exists")
        identity = candidate_identity()
    code = run_logged(
        [sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()), "--preflight"],
        log_dir / "preflight.log", cwd=ROOT, timeout=45,
    )
    if code:
        return code
    code = run_logged(
        [sys.executable, "-X", "utf8", "-B", "-m", "unittest", "discover", "-v"],
        log_dir / "unittest.log", cwd=ROOT, timeout=900,
    )
    if code == 0 and candidate_receipt:
        if candidate_identity() != identity:
            raise ValueError("Source or native DLL changed during regression")
        save_receipt(log_dir / "regression.json", log_dir / "unittest.log", identity)
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, default=Path("ci-logs"))
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--candidate-receipt", action="store_true")
    args = parser.parse_args(argv)
    if args.preflight:
        preflight()
        return 0
    return run_ci(args.log_dir, candidate_receipt=args.candidate_receipt)


if __name__ == "__main__":
    raise SystemExit(main())
