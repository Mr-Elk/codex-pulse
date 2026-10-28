"""Load and exercise the freshly built Windows DLL; no user settings are changed."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from distribution.windows_candidate import DLL, check_amd64_dll
from release_policy import clean_revision
from release_tools import digest


def check_native(output):
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        raise ValueError("Native acceptance requires 64-bit Windows Python")
    revision = clean_revision(ROOT)
    if revision is None or Path(output).exists():
        raise ValueError("Use clean source and a new native smoke receipt path")
    data = (ROOT / DLL).read_bytes()
    check_amd64_dll(data)
    from native_backdrop import Backdrop, user
    backdrop = Backdrop()
    hwnd = backdrop.hwnd
    try:
        if not backdrop.available:
            raise ValueError("Real composition unavailable: " + str(backdrop.reason))
        # Exercise the actual exported API and HRESULT failure contract.
        library = backdrop.library
        if library.pulse_blur_resize(backdrop.instance, 300, 48) < 0:
            raise ValueError("Native rounded geometry resize failed")
        if library.pulse_blur_resize(backdrop.instance, 0, 48) >= 0:
            raise ValueError("Native API accepted invalid geometry")
        if library.pulse_blur_create(None, None) >= 0:
            raise ValueError("Native API accepted a missing output pointer")
    finally:
        backdrop.close()
    if hwnd and user.IsWindow(hwnd):
        raise ValueError("Native smoke check leaked its window")
    if clean_revision(ROOT) != revision or (ROOT / DLL).read_bytes() != data:
        raise ValueError("Source or DLL changed during native smoke check")
    result = {"schema": 1, "platform": "windows-x64", "source_revision": revision,
              "dll_sha256": digest(data), "windows_build": sys.getwindowsversion().build,
              "checks": {"load_exports": True, "create": True, "resize": True, "destroy": True}}
    with Path(output).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.worker:
        try:
            return subprocess.run([sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()),
                                   "--worker", "--output", str(args.output.resolve())], timeout=45).returncode
        except subprocess.TimeoutExpired:
            print("Native check timed out after 45 seconds; candidate build stopped.", file=sys.stderr)
            return 124
    try:
        print(json.dumps(check_native(args.output), indent=2))
    except (OSError, ValueError) as error:
        print(f"Native check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
