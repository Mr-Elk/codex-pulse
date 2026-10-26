"""Shared, stable layout for the Windows strip and its exact image preview."""
from dataclasses import dataclass

from overlay_geometry import compact

ROW_HEIGHT = 40
HEIGHT = ROW_HEIGHT
INSET = 36
CELL_PADDING = 8
ICON_SIZE = 18
ICON_GAP = 6
CELL_TRAILING = 10


def control_at(x, y, width, height, scale=1, capsule=False):
    """Keep the two visible controls usable while metric cells pass clicks through."""
    if not (0 <= x < width and 0 <= y < height):
        return None
    edge = round(INSET * scale)
    if x < edge:
        return "drag"
    if not capsule and x >= width - edge:
        return "menu"
    return None
COLUMN_WIDTHS = {"rounds": 152, "speed": 152, "tokens": 162, "cache": 126, "context": 160}
ARENA_KEYS=("recent","quota","reset","credits")
COLUMN_WIDTHS.update(tokens=80,speed=99,context=68,cache=68,rounds=89,recent=93,quota=78,reset=76,credits=60)
ORDER = ("speed", "tokens", "cache", "context", "rounds")
ALL_ORDER=ARENA_KEYS+ORDER
WIDTH = 2 * INSET + sum(COLUMN_WIDTHS[k] for k in ORDER) + 6
LABELS = {"rounds": "轮次 / 请求数", "speed": "TPS 估算", "tokens": "累计 Token", "cache": "缓存命中率", "context": "上下文估算"}
LABELS.update(recent="最近 X 小时用量",quota="账户剩余额度",reset="自然重置时间",credits="重置卡数量")


def normalize_keys(keys):
    if not isinstance(keys, (list, tuple)):
        return ORDER
    if not keys:return ()
    selected = tuple(dict.fromkeys(key for key in keys if key in ALL_ORDER))
    return selected or ORDER


def width_for(keys=None):
    selected = normalize_keys(keys)
    if not selected:return 280
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


def token_runs(value):
    rendered=compact(value)
    if rendered.endswith(('M','k')):return (Run(rendered[:-1],'value',1),Run(rendered[-1],'label',1))
    return (Run(rendered),)

def percent_runs(value):
    return (Run(f'{value:.0f}','value',1),Run('%','label',1)) if value is not None else (Run('—'),)

def metrics(snapshot):
    account=(snapshot or {}).get("quota_display") or {}
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
                  (Run(f"{speed:.1f}" if speed is not None else "—", "speed", 1), Run("tok/s", "label")))
    data = {
        "rounds": Metric("rounds", (Run(str(snapshot.get("rounds", "—")), gap=1), Run("/", "label", 1), Run(str(snapshot.get("requests", "—"))))),
        "speed": Metric("speed", speed_runs),
        "tokens": Metric("tokens", token_runs(snapshot.get("usage", {}).get("total_tokens"))),
        "cache": Metric("cache", percent_runs(cache)),
        "context": Metric("context", percent_runs(context), context),
    }
    def account_runs(key,fallback):
        parts=(account.get('parts') or {}).get(key) or []
        return tuple(Run(text,role,1) for text,role in parts) if parts else (Run(account.get(key,fallback)),)
    data.update({"quota":Metric("quota",account_runs('quota','额度 —')),
        "recent":Metric("recent",account_runs('recent','近期用量 —')),
        "reset":Metric("reset",account_runs("reset","—")),
        "credits":Metric("credits",account_runs('credits','重置卡 —'))})
    return {key: data[key] for key in selected}


def columns(width, minimums=None, selected=None):
    """Fixed columns in normal use. Drop less important fields before clipping."""
    sizes = dict(COLUMN_WIDTHS)
    if minimums:
        sizes.update({key: max(sizes[key], value) for key, value in minimums.items()})
    keys = list(normalize_keys(selected))
    if not keys:return []
    available = max(0, width - 2 * INSET)
    for key in ("rounds", "context", "cache", "tokens", "speed","credits","reset","quota","recent"):
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
