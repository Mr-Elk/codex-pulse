"""Shared local settings I/O: preserve failed reads and replace atomically."""
import json
import os
from pathlib import Path
import uuid


class SettingsFormatError(ValueError):
    """An existing settings document could not be safely interpreted for an update."""


def read_document(path: Path) -> tuple[dict, bytes | None]:
    """Return one consistent document/raw snapshot; only a missing file is empty."""
    try:
        original = path.read_bytes()
    except FileNotFoundError:
        return {}, None
    try:
        document = json.loads(original.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SettingsFormatError("设置文件无法解析，原文件已保留") from error
    if not isinstance(document, dict):
        raise SettingsFormatError("设置文件格式不可用，原文件已保留")
    return document, original


def write_document(path: Path, document: dict) -> None:
    """Use an owned temporary file so a failed save cannot replace another writer's."""
    contents = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(contents)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
