"""Shared, stable layout for the Windows strip and its exact image preview."""
from dataclasses import dataclass

from overlay_geometry import compact

ROW_HEIGHT = 48
HEIGHT = ROW_HEIGHT + 8
INSET = 34
CELL_PADDING = 8
ICON_SIZE = 24
ICON_GAP = 8
CELL_TRAILING = 10


def control_at(x, y, width, height, scale=1):
    """Keep the two visible controls usable while metric cells pass clicks through."""
    if not (0 <= x < width and 0 <= y < height):
        return None
    edge = round(INSET * scale)
    if x < edge:
        return "drag"
    if x >= width - edge:
        return "menu"
    return None
COLUMN_WIDTHS = {"rounds": 152, "speed": 152, "tokens": 162, "cache": 126, "context": 160}
WIDTH = 2 * INSET + sum(COLUMN_WIDTHS.values()) + 6
ORDER = ("speed", "tokens", "cache", "context", "rounds")
LABELS = {"rounds": "轮次 / 请求数", "speed": "TPS 估算", "tokens": "累计 Token", "cache": "缓存命中率", "context": "上下文估算"}


def normalize_keys(keys):
    if not isinstance(keys, (list, tuple)):
        return ORDER
    selected = tuple(key for key in ORDER if key in keys)
    return selected or ORDER


def width_for(keys=None):
    selected = normalize_keys(keys)
    return 2 * INSET + sum(COLUMN_WIDTHS[key] for key in selected) + 6


@dataclass(frozen=True)
class Run:
    text: str
    role: str = "value"
    gap: int = 4


@dataclass(frozen=True)
class Metric:
    key: str
    runs: tuple
    progress: float | None = None


@dataclass(frozen=True)
class Column:
    key: str
    x: float
    width: float


def metrics(snapshot):
    selected = normalize_keys((snapshot or {}).get("visible_metrics"))
    available = bool(snapshot and snapshot.get("available"))
    if not available:
        snapshot = {"request_pending":bool(snapshot and snapshot.get("request_pending"))}
    speed = snapshot.get("latest_tps_estimate")
    cache = snapshot.get("cache_hit_percent")
    context = snapshot.get("context_percent_estimate")
    percent = lambda value: f"{value:.0f}%" if value is not None else "—"
    speed_runs = ((Run("刷新中", "label"),) if snapshot.get("speed_refreshing") else
                  (Run("生成中", "label"),) if snapshot.get("request_pending") else
                  (Run(f"≈ {speed:.1f}" if speed is not None else "—", "speed", 5), Run("tok/s", "label")))
    data = {
        "rounds": Metric("rounds", (Run(str(snapshot.get("rounds", "—")), gap=2), Run("轮 /", "label", 3),
                                    Run(str(snapshot.get("requests", "—")), gap=2), Run("次", "label"))),
        "speed": Metric("speed", speed_runs),
        "tokens": Metric("tokens", (Run(compact(snapshot.get("usage", {}).get("total_tokens"))), Run("Token", "label"))),
        "cache": Metric("cache", (Run("缓存", "label"), Run(percent(cache)))),
        "context": Metric("context", (Run("上下文", "label"), Run(("≈ " + percent(context)) if context is not None else "—")), context),
    }
    return {key: data[key] for key in selected}


def columns(width, minimums=None, selected=None):
    """Fixed columns in normal use. Drop less important fields before clipping."""
    sizes = dict(COLUMN_WIDTHS)
    if minimums:
        sizes.update({key: max(sizes[key], value) for key, value in minimums.items()})
    keys = list(normalize_keys(selected))
    available = max(0, width - 2 * INSET)
    for key in ("rounds", "context", "cache", "tokens", "speed"):
        # Rounding a scaled window to physical pixels can lose <1 design pixel.
        if sum(sizes[k] for k in keys) <= available + 1:
            break
        if key in keys and len(keys) > 1:
            keys.remove(key)
    total = sum(sizes[k] for k in keys)
    if total > available + 1:
        return []
    extra = (available - total) / len(keys)
    x, result = float(INSET), []
    for key in keys:
        size = sizes[key] + extra
        result.append(Column(key, x, size))
        x += size
    return result
