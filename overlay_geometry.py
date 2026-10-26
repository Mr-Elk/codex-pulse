"""Placement and display logic, independent of Windows and the GUI."""
from dataclasses import dataclass
import ui_tokens as ui


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


def place(window, width, height, composer=None, manual=None, scale=1,capsule=False):
    """Anchor above composer, or preserve a user placement within the app."""
    width = min(width, max(1, window.width - round(16 * scale)))
    if composer and capsule:
        width = min(width, max(1, composer.width - round(48 * scale)))
    if composer:
        anchored=manual if manual and manual.get('anchor')=='composer' else {}
        ratio=anchored.get('left_ratio',anchored.get('capsule_left_ratio'))
        if ratio is not None:x=composer.left+round(composer.width*ratio)
        else:x=composer.left+round(ui.COMPOSER_CAPSULE_INSET*scale)
        y=composer.top-round(anchored.get('gap',7)*scale)-height
        if capsule:x=max(composer.left,min(x,composer.right-width))
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
                "left_ratio":max(0,min(1,(overlay.left-composer.left)/composer.width)),
                "gap": max(0,(composer.top-overlay.bottom)/scale)}
    return {"center_ratio": (overlay.left + overlay.width / 2 - window.left) / window.width,
            "bottom_gap": (window.bottom - overlay.bottom) / scale}


def remember_capsule(window,overlay,manual=None,scale=1,composer=None):
    """A capsule drag must not replace the expanded strip's horizontal anchor."""
    if composer is None:return remember(window,overlay,scale)
    value=remember(window,overlay,scale,composer)
    value['center_ratio']=manual.get('center_ratio',.5) if manual and manual.get('anchor')=='composer' else .5
    value['capsule_left_ratio']=max(0,min(1,(overlay.left-composer.left)/composer.width))
    return value


def panel_bounds(area,anchor,width,height,scale=1):
    """Keep the panel beside its strip, moving only to remain on screen."""
    margin=min(round(ui.PANEL_MARGIN*scale),max(0,(area.height-round(320*scale))//2))
    width=min(width,area.width);height=min(height,max(1,area.height-2*margin))
    left=max(area.left,min(anchor.left,area.right-width))
    gap=round(ui.PANEL_ANCHOR_GAP*scale)
    above_space=anchor.top-gap-(area.top+margin)
    below=anchor.bottom+gap;below_space=area.bottom-margin-below
    if above_space>=round(320*scale):
        height=min(height,above_space);top=anchor.top-gap-height
    elif below_space>=round(320*scale):
        height=min(height,below_space);top=below
    else:top=anchor.top-gap-height
    top=max(area.top+margin,min(top,area.bottom-margin-height))
    return Rect(left,top,left+width,top+height)


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


class DesktopAnchor:
    """Keep live value-width changes on the same left edge, without saving them."""
    def __init__(self):
        self.key = self.rect = None

    def place(self, window, width, height, manual=None, scale=1):
        candidate = place(window,width,height,manual=manual,scale=scale)
        key = (window,scale,tuple(sorted((manual or {}).items())))
        if key == self.key and self.rect is not None:
            resized = resize_from_left(self.rect,candidate.width,candidate.height)
            left=max(window.left,min(resized.left,window.right-resized.width))
            top=max(window.top,min(resized.top,window.bottom-resized.height))
            candidate=Rect(left,top,left+resized.width,top+resized.height)
        self.key,self.rect=key,candidate
        return candidate


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
