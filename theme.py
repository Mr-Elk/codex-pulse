"""Local accent themes. Keep approved geometry, white borders and neutral text."""
import colorsys
from collections import OrderedDict
from functools import lru_cache
import json
import re

DEFAULT = "#8b57f1"
PRESETS = (
    ("紫藤", DEFAULT), ("海蓝", "#3f78db"), ("青绿", "#168578"), ("玫瑰", "#c34c86"),
    ("靛青", "#5256c7"), ("湖青", "#168aa0"), ("森林", "#36824b"), ("橄榄", "#788532"),
    ("琥珀", "#b58018"), ("暖橙", "#cd702b"), ("珊瑚", "#c65350"), ("岩灰", "#66788c"),
)
_accent = DEFAULT
_roles = OrderedDict()


def normalize(value):
    return value.lower() if isinstance(value,str) and re.fullmatch(r"#[0-9a-fA-F]{6}",value) else DEFAULT


def load(path):
    try:
        value=json.loads(path.read_text(encoding="utf-8"))
        return normalize(value.get("theme_color"))
    except (OSError,ValueError,AttributeError):
        return DEFAULT


def activate(accent):
    global _accent
    previous=_accent
    _accent=normalize(accent)
    if previous!=_accent:
        # Asset PNGs depend on the active palette as well as their dimensions.
        from svg_art import render_asset
        render_asset.cache_clear()
    _roles.setdefault(_accent,{})
    _roles.move_to_end(_accent)
    while len(_roles)>16:
        _roles.popitem(last=False)
    return _accent


def current():
    return _accent


def luminance(rgb):
    linear=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb]
    return sum(c*w for c,w in zip(linear,(.2126,.7152,.0722)))


@lru_cache(maxsize=1024)
def resolve(value, accent):
    if accent==DEFAULT or not re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?",value):
        return value
    alpha,pixels=(value[1:3],value[3:]) if len(value)==9 else ("",value[1:])
    rgb=tuple(int(pixels[i:i+2],16)/255 for i in (0,2,4))
    hue,light,saturation=colorsys.rgb_to_hls(*rgb)
    # Only the existing purple/blue design palette changes. White contours,
    # dark numeric ink, and semantic green/amber messages keep their meaning.
    if not 225/360<=hue<=285/360 or saturation<.055 or light<.19:
        return value
    seed=tuple(int(accent[i:i+2],16)/255 for i in (1,3,5))
    next_hue,_,next_sat=colorsys.rgb_to_hls(*seed)
    next_rgb=colorsys.hls_to_rgb(next_hue,light,min(.95,saturation*max(.25,next_sat)/.846))
    old_contrast=1.05/(luminance(rgb)+.05)
    minimum=min(4.5,old_contrast) if old_contrast>=3 else 1
    while 1.05/(luminance(next_rgb)+.05)<minimum and max(next_rgb)>.01:
        next_rgb=tuple(c*.97 for c in next_rgb)
    return "#"+alpha+"".join(f"{round(c*255):02x}" for c in next_rgb)


def color(value):
    if isinstance(value,list):
        return [color(item) for item in value]
    if isinstance(value,tuple):
        return tuple(color(item) for item in value)
    if not isinstance(value,str):
        return value
    roles=_roles.setdefault(_accent,{})
    if value in roles:
        return value
    converted=resolve(value,_accent)
    if converted!=value:
        roles[converted]=value
    return converted


def repaint(panel, previous):
    """Repaint this app's existing widgets; keep the window and selected tab."""
    # Keep canonical roles for exact repeated changes and restoration. Reading
    # current widget options also picks up labels/controls rebuilt on tab changes.
    roles=getattr(panel,"theme_roles",{})
    stack=[panel.window]
    live=set()
    options=("background","foreground","activebackground","activeforeground",
             "disabledforeground","insertbackground","highlightbackground","highlightcolor")
    while stack:
        widget=stack.pop()
        live.add(str(widget))
        stack.extend(widget.winfo_children())
        available=widget.keys()
        for option in options:
            if option not in available:
                continue
            key=(str(widget),option)
            value=str(widget.cget(option))
            canonical,last=roles.get(key,(_roles.get(previous,{}).get(value,value),value))
            if value!=last:
                canonical=_roles.get(previous,{}).get(value,value)
            converted=color(canonical)
            if converted!=value:
                widget.configure(**{option:converted})
            roles[key]=(canonical,converted)
        # SVG surfaces also keep a fill outside Tk's options. Panels created
        # while a saved non-purple theme is active must not retain that tint.
        if hasattr(widget,"fill") and isinstance(widget.fill,str):
            key=(str(widget),"@fill")
            value=widget.fill
            canonical,last=roles.get(key,(_roles.get(previous,{}).get(value,value),value))
            if value!=last:
                canonical=_roles.get(previous,{}).get(value,value)
            widget.fill=color(canonical)
            roles[key]=(canonical,widget.fill)
        if hasattr(widget,"signature"):
            widget.signature=None
        if hasattr(widget,"redraw"):
            widget.redraw()
        elif hasattr(widget,"draw"):
            from types import SimpleNamespace
            from panel_widgets import Surface
            if isinstance(widget,Surface):
                widget.draw(SimpleNamespace(width=widget.winfo_width(),height=widget.winfo_height()))
            else:
                widget.draw()
    panel.theme_roles={key:value for key,value in roles.items() if key[0] in live}
    if panel.tab=="session":
        panel.configure_session_tree()
