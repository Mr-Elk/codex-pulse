"""Small, version-independent preferences for the floating strip."""
import json
import math
import os
from pathlib import Path
from overlay_style import normalize_keys, ORDER
import theme

FONT_SIZES = (13, 15, 17)
DEFAULT_FONT_SIZE = 15


def default_path():
    # Private installer metadata keeps packaged-app and Explorer launches on the
    # same resolved files. The pointer is excluded from distributable packages.
    try:
        local = json.loads(Path(__file__).with_name(".codex-pulse-local.json").read_text(encoding="utf-8-sig"))
        recorded = Path(local.get("settings_file", ""))
        if recorded.is_absolute() and recorded.name == "settings.json" and recorded.parent.name == "CodexPulse":
            return recorded.resolve()
    except (OSError, ValueError, TypeError):
        pass
    folder = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return (folder / "CodexPulse" / "settings.json").resolve()


def valid_position(value):
    if not isinstance(value, dict):
        return None
    anchored = value.get("anchor") == "composer"
    center, gap = value.get("center_ratio"), value.get("gap" if anchored else "bottom_gap")
    if (type(center) in (int, float) and type(gap) in (int, float)
            and math.isfinite(center) and math.isfinite(gap)
            and 0 <= center <= 1 and 0 <= gap <= 4000):
        return {"anchor":"composer","center_ratio":center,"gap":gap} if anchored else {"center_ratio": center, "bottom_gap": gap}
    return None


def load(path, legacy=None):
    result = {"font_size": DEFAULT_FONT_SIZE, "position": None, "locked": True, "visible_metrics": list(ORDER)}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            size = value.get("font_size")
            if type(size) is int and size in FONT_SIZES:
                result["font_size"] = size
            result["position"] = valid_position(value.get("position"))
            result["locked"] = value.get("locked", True) if type(value.get("locked", True)) is bool else True
            result["visible_metrics"] = list(normalize_keys(value.get("visible_metrics")))
        return result
    except (OSError, ValueError):
        pass
    if legacy:
        try:
            result["position"] = valid_position(json.loads(legacy.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return result


def load_display(path):
    result = {"mode":"composer", "position":None, "compact":True, "animations":True,
              "expanded_mode":"composer"}
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("display", {})
        if isinstance(value, dict):
            result["mode"] = value.get("mode") if value.get("mode") in ("composer","desktop") else "composer"
            result["expanded_mode"] = value.get("expanded_mode") if value.get("expanded_mode") in ("composer","desktop") else result["mode"]
            result["position"] = valid_position(value.get("position"))
            for key in ("compact","animations"):
                if type(value.get(key)) is bool:
                    result[key] = value[key]
    except (OSError,ValueError,AttributeError):
        pass
    return result


def save(path, font_size, position, locked=True, visible_metrics=None, display=None, theme_color=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {}
    old_bytes = None
    try:
        old_bytes = path.read_bytes()
        old = json.loads(old_bytes.decode("utf-8"))
        if isinstance(old, dict):
            value = old
    except (OSError, ValueError):
        pass
    if old_bytes is not None and value.get("version", 1) == 1:
        backup = path.with_name(path.stem + ".v1.backup.json")
        try:
            with backup.open("xb") as stream:
                stream.write(old_bytes)
        except FileExistsError:
            pass
    value.update(version=2, font_size=font_size, position=valid_position(position),
                 locked=bool(locked), visible_metrics=list(normalize_keys(visible_metrics)))
    if display is not None:
        value["display"] = display
    if theme_color is not None:
        value["theme_color"] = theme.normalize(theme_color)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
