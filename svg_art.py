"""Render the small, audited SVG vocabulary used by our bundled UI assets.

No browser, network, external images or font-to-path conversion. GDI+ draws
the SVG shapes; the strip draws live text separately at the monitor's pixels.
This deliberately rejects SVG features outside the bundled asset vocabulary.
"""
from functools import lru_cache
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ASSETS = Path(__file__).with_name("assets")


@lru_cache(maxsize=32)
def asset(name):
    path = (ASSETS / name).resolve()
    if path.parent != ASSETS.resolve() or path.suffix != ".svg":
        raise ValueError("Expected a bundled SVG asset")
    return ET.fromstring(path.read_text(encoding="utf-8"))


def number(value, extent):
    match = re.fullmatch(r"calc\((\d+(?:\.\d+)?)% - (\d+(?:\.\d+)?)px\)", value)
    if match:
        return float(match[1])*extent/100-float(match[2])
    return float(value[:-1])*extent/100 if value.endswith("%") else float(value)


def paint(renderer, name, x, y, width, height, palette=None):
    from strip_renderer import C, W, F, P, RectF, bind, call, color
    bind("GdipSaveGraphics", [P, C.POINTER(W.UINT)])
    bind("GdipRestoreGraphics", [P, W.UINT])
    bind("GdipAddPathLine", [P, F, F, F, F])
    bind("GdipAddPathBezier", [P] + [F]*8)
    bind("GdipStartPathFigure", [P])
    bind("GdipCreateLineBrushFromRect", [C.POINTER(RectF), W.UINT, W.UINT, C.c_int, C.c_int, C.POINTER(P)])
    root, palette = asset(name), palette or {}
    view = list(map(float, root.get("viewBox", f"0 0 {width} {height}").split()))
    if view[:2] != [0, 0]:
        raise ValueError("Asset viewBox must start at zero")
    vw, vh = view[2:]
    gradients = {n.get("id"): n for n in root.iter() if n.tag.split("}")[-1] == "linearGradient"}

    def ink(value, opacity="1"):
        value = palette.get(value, value)
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError(f"Unsupported SVG color: {value}")
        return f"#{round(float(opacity)*255):02x}" + value[1:]

    def brush(node, bounds):
        fill = node.get("fill", "#000000")
        if fill.startswith("url(#") and fill.endswith(")"):
            gradient = gradients[fill[5:-1]]
            stops = list(gradient)
            if len(stops) != 2 or [s.get("offset") for s in stops] != ["0", "1"]:
                raise ValueError("Expected two gradient endpoints")
            values = [color(ink(s.get("stop-color"), s.get("stop-opacity", "1"))) for s in stops]
            # All our materials use a vertical, object-bounding-box gradient.
            if gradient.get("x2") != "0" or gradient.get("y2") != "1":
                raise ValueError("Expected vertical SVG gradient")
            return renderer.new("GdipCreateLineBrushFromRect", "GdipDeleteBrush",
                                C.byref(RectF(*bounds)), *values, 1, 0)
        return renderer.brush(ink(fill, node.get("fill-opacity", "1")))

    state = W.UINT()
    call("GdipSaveGraphics", renderer.g, C.byref(state))
    try:
        call("GdipTranslateWorldTransform", renderer.g, x, y, 0)
        call("GdipScaleWorldTransform", renderer.g, width/vw, height/vh, 0)
        for node in root:
            tag = node.tag.split("}")[-1]
            if tag == "defs":
                continue
            if tag in ("rect", "circle", "ellipse"):
                if tag == "rect":
                    px, py = number(node.get("x", "0"), vw), number(node.get("y", "0"), vh)
                    w, h = number(node.get("width"), vw), number(node.get("height"), vh)
                    radius = min(float(node.get("rx", "0")), w/2, h/2)
                else:
                    rx = float(node.get("r", node.get("rx", "0")))
                    ry = float(node.get("r", node.get("ry", "0")))
                    px, py = float(node.get("cx"))-rx, float(node.get("cy"))-ry
                    w, h, radius = 2*rx, 2*ry, None
                path = renderer.new("GdipCreatePath", "GdipDeletePath", 0)
                if radius is None:
                    bind("GdipAddPathEllipse", [P, F, F, F, F])
                    call("GdipAddPathEllipse", path, px, py, w, h)
                elif radius:
                    d = 2*radius
                    for ax, ay, angle in ((px,py,180),(px+w-d,py,270),(px+w-d,py+h-d,0),(px,py+h-d,90)):
                        call("GdipAddPathArc", path, ax, ay, d, d, angle, 90)
                else:
                    bind("GdipAddPathRectangle", [P, F, F, F, F])
                    call("GdipAddPathRectangle", path, px, py, w, h)
                call("GdipClosePathFigure", path)
                bounds = (px, py, w, h)
            elif tag == "path":
                path = renderer.new("GdipCreatePath", "GdipDeletePath", 0)
                tokens = re.findall(r"[A-Za-z]|-?(?:\d*\.\d+|\d+)", node.get("d", ""))
                index, point, start = 0, (0,0), (0,0)
                while index < len(tokens):
                    command = tokens[index]; index += 1
                    count = {"M":2, "L":2, "C":6, "Z":0}.get(command)
                    if count is None:
                        raise ValueError(f"Unsupported SVG path command: {command}")
                    values = tuple(map(float, tokens[index:index+count])); index += count
                    if command == "M":
                        call("GdipStartPathFigure", path)
                        point = start = values
                    elif command == "L":
                        call("GdipAddPathLine", path, *point, *values); point = values
                    elif command == "C":
                        call("GdipAddPathBezier", path, *point, *values); point = values[-2:]
                    else:
                        call("GdipClosePathFigure", path); point = start
                bounds = (0,0,vw,vh)
            else:
                raise ValueError(f"Unsupported SVG element: {tag}")
            if node.get("fill", "#000000") != "none":
                call("GdipFillPath", renderer.g, brush(node, bounds), path)
            if node.get("stroke", "none") != "none":
                pen = renderer.pen(ink(node.get("stroke"), node.get("stroke-opacity", "1")), float(node.get("stroke-width", "1")))
                bind("GdipSetPenLineCap197819", [P, C.c_int, C.c_int, C.c_int])
                bind("GdipSetPenLineJoin", [P, C.c_int])
                cap = {"butt":0,"square":1,"round":2}[node.get("stroke-linecap",root.get("stroke-linecap","butt"))]
                join = {"miter":0,"bevel":1,"round":2}[node.get("stroke-linejoin",root.get("stroke-linejoin","miter"))]
                call("GdipSetPenLineCap197819", pen, cap, cap, 0)
                call("GdipSetPenLineJoin", pen, join)
                call("GdipDrawPath", renderer.g, pen, path)
    finally:
        call("GdipRestoreGraphics", renderer.g, state)


@lru_cache(maxsize=128)
def render_asset(name, width, height, scale=1, fill=None, background=None):
    from strip_renderer import Renderer,call,color
    renderer = Renderer(width, scale, height=height)
    try:
        if background:call("GdipGraphicsClear",renderer.g,color(background))
        paint(renderer, name, 0, 0, width/scale, height/scale,
              {"currentColor":fill} if fill else None)
        return renderer.png()
    finally:
        renderer.close()
