"""Placement and display logic, independent of Windows and the GUI."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top


def place(window, width, height, composer=None, manual=None, scale=1):
    """Anchor above composer, or preserve a user placement within the app."""
    width = min(width, max(1, window.width - round(16 * scale)))
    if composer:
        width = min(width, max(1, composer.width - round(48 * scale)))
    if manual and manual.get("anchor") == "composer" and composer:
        x = composer.left + round(composer.width * manual["center_ratio"] - width / 2)
        y = composer.top - round(manual["gap"] * scale) - height
    elif manual and manual.get("anchor") != "composer":
        x = window.left + round(window.width * manual["center_ratio"] - width / 2)
        y = window.bottom - round(manual["bottom_gap"] * scale) - height
    elif composer:
        x = composer.left + (composer.width - width) // 2
        y = composer.top - height - round(7 * scale)
    else:
        x = window.left + (window.width - width) // 2
        y = window.bottom - round(166 * scale)
    x = max(window.left, min(x, window.right - width))
    y = max(window.top, min(y, window.bottom - height))
    return Rect(x, y, x + width, y + height)


def remember(window, overlay, scale=1, composer=None):
    if composer:
        return {"anchor":"composer", "center_ratio": (overlay.left+overlay.width/2-composer.left)/composer.width,
                "gap": max(0,(composer.top-overlay.bottom)/scale)}
    return {"center_ratio": (overlay.left + overlay.width / 2 - window.left) / window.width,
            "bottom_gap": (window.bottom - overlay.bottom) / scale}


def stable_position(previous, candidate, tolerance=2):
    """Ignore small UIA coordinate noise, never size changes or accumulated moves."""
    if (previous and previous.width == candidate.width and previous.height == candidate.height
            and abs(previous.left-candidate.left) <= tolerance
            and abs(previous.top-candidate.top) <= tolerance):
        return previous
    return candidate


def resize_from_left(rect, width, height):
    """Keep the left edge and its vertical midpoint while resizing rightward."""
    top=round((rect.top+rect.bottom-height)/2)
    return Rect(rect.left,top,rect.left+width,top+height)


def compact(value):
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


def segments(snapshot):
    if not snapshot or not snapshot.get("available"):
        return ["等待当前对话记录", "TPS —"]
    tps = snapshot["latest_tps_estimate"]
    speed = f"≈ {tps:.1f} tok/s" if tps is not None else "TPS —"
    cache = snapshot["cache_hit_percent"]
    context = snapshot["context_percent_estimate"]
    return [f"{snapshot['rounds']} 轮 {snapshot['requests']} 次",
            speed, compact(snapshot["usage"]["total_tokens"]) + " tok",
            "缓存 " + (f"{cache:.0f}%" if cache is not None else "—"),
            "上下文 ≈" + (f"{context:.0f}%" if context is not None else "—")]
