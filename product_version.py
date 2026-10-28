"""Product identity comes from product metadata, never a shared engine constant."""
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent


def validate_version(value):
    if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?", value):
        raise ValueError("Invalid product version")
    return value


def windows_version(root=ROOT):
    metadata = json.loads((Path(root) / "plugin.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("name") != "codex-pulse":
        raise ValueError("Windows product metadata is invalid")
    return validate_version(metadata.get("version"))
