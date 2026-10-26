"""Quota and capsule preferences, independent of workers, storage and native UI."""
import json


DEFAULTS = {
    "group": None,
    "window": "primary",
    "hours": 1,
    "capsule": "quota",
    "reminder": {"enabled": False, "source": "focus", "threshold": 20},
}
METRIC_KEYS = (
    "tokens", "speed", "context", "cache", "rounds",
    "quota", "recent", "reset", "credits",
)


def clean_config(value):
    """Return independent preferences, preserving legacy task-capsule defaults."""
    value = value if isinstance(value, dict) else {}
    reminder = value.get("reminder")
    reminder = reminder if isinstance(reminder, dict) else {}
    hours = value.get("hours")
    threshold = reminder.get("threshold")
    primary = value.get("capsule_primary")
    if primary not in METRIC_KEYS:
        primary = "tokens" if value.get("capsule") == "task" else "quota"
    secondary = value.get("capsule_secondary") if "capsule_secondary" in value else (
        "speed" if value.get("capsule") == "task" else "recent"
    )
    if secondary not in METRIC_KEYS or secondary == primary:
        secondary = None
    return {
        "group": value.get("group") if isinstance(value.get("group"), str) else None,
        "window": value.get("window") if value.get("window") in ("primary", "secondary") else "primary",
        "hours": hours if type(hours) is int and 1 <= hours <= 168 else 1,
        "capsule": value.get("capsule") if value.get("capsule") in ("quota", "task") else "quota",
        "capsule_primary": primary,
        "capsule_secondary": secondary,
        "reminder": {
            "enabled": reminder.get("enabled") is True,
            "source": reminder.get("source") if reminder.get("source") in (
                "focus", "primary", "secondary", "any"
            ) else "focus",
            "threshold": threshold if type(threshold) is int and 0 <= threshold <= 100 else 20,
        },
    }


def load_config(path):
    """Read preferences without repairing or overwriting a user's source file."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return clean_config(None)
    return clean_config(document.get("quota") if isinstance(document, dict) else None)


def reminder_rule(config):
    config = clean_config(config)
    return {
        "group": config["group"],
        "window": config["window"] if config["reminder"]["source"] == "focus" else None,
        "reminder": config["reminder"],
    }
