"""Render our own toolbar with built-in Windows GDI+, without extra packages.

The exported PNG is the same image displayed in the floating window. It is an
offscreen rendering of our own code, never a desktop/window screenshot.
"""
from __future__ import annotations

import atexit
import ctypes as C
from ctypes import wintypes as W
import struct
import zlib

from overlay_style import HEIGHT, ROW_HEIGHT, CELL_PADDING, ICON_SIZE, ICON_GAP, CELL_TRAILING, columns, metrics
from font_policy import family as ui_font_family
import theme

P = C.c_void_p
F = C.c_float
ARGB = 0x26200A
METRIC_INK = "#69708f"


class RectF(C.Structure):
    _fields_ = [(key, F) for key in ("x", "y", "width", "height")]


class RectI(C.Structure):
    _fields_ = [(key, C.c_int) for key in ("x", "y", "width", "height")]


class BitmapData(C.Structure):
    _fields_ = [("width", W.UINT), ("height", W.UINT), ("stride", C.c_int),
                ("format", C.c_int), ("scan", P), ("reserved", C.c_size_t)]


class StartupInput(C.Structure):
    _fields_ = [("version", W.UINT), ("callback", P), ("suppress_thread", W.BOOL), ("suppress_codecs", W.BOOL)]


api = C.WinDLL("gdiplus")


def bind(name, args):
    function = getattr(api, name)
    function.argtypes, function.restype = args, C.c_int
    return function


def call(name, *args):
    status = getattr(api, name)(*args)
    if status:
        raise OSError(f"GDI+ {name}: {status}")


for name, args in {
    "GdiplusStartup": [C.POINTER(C.c_size_t), C.POINTER(StartupInput), P],
    "GdipCreateBitmapFromScan0": [C.c_int, C.c_int, C.c_int, C.c_int, P, C.POINTER(P)],
    "GdipGetImageGraphicsContext": [P, C.POINTER(P)],
    "GdipGraphicsClear": [P, W.UINT],
    "GdipSetSmoothingMode": [P, C.c_int],
    "GdipSetTextRenderingHint": [P, C.c_int],
    "GdipSetInterpolationMode": [P, C.c_int],
    "GdipSetPixelOffsetMode": [P, C.c_int],
    "GdipScaleWorldTransform": [P, F, F, C.c_int],
    "GdipTranslateWorldTransform": [P, F, F, C.c_int],
    "GdipCreateSolidFill": [W.UINT, C.POINTER(P)],
    "GdipCreatePen1": [W.UINT, F, C.c_int, C.POINTER(P)],
    "GdipCreatePath": [C.c_int, C.POINTER(P)],
    "GdipAddPathArc": [P, F, F, F, F, F, F],
    "GdipClosePathFigure": [P],
    "GdipFillPath": [P, P, P],
    "GdipDrawPath": [P, P, P],
    "GdipDrawEllipse": [P, P, F, F, F, F],
    "GdipFillEllipse": [P, P, F, F, F, F],
    "GdipDrawLine": [P, P, F, F, F, F],
    "GdipDrawArc": [P, P, F, F, F, F, F, F],
    "GdipCreateFontFamilyFromName": [W.LPCWSTR, P, C.POINTER(P)],
    "GdipCreateFont": [P, F, C.c_int, C.c_int, C.POINTER(P)],
    "GdipGetCellAscent": [P, C.c_int, C.POINTER(W.WORD)],
    "GdipGetCellDescent": [P, C.c_int, C.POINTER(W.WORD)],
    "GdipGetEmHeight": [P, C.c_int, C.POINTER(W.WORD)],
    "GdipStringFormatGetGenericTypographic": [C.POINTER(P)],
    "GdipSetStringFormatFlags": [P, C.c_int],
    "GdipMeasureString": [P, W.LPCWSTR, C.c_int, P, C.POINTER(RectF), P, C.POINTER(RectF), P, P],
    "GdipDrawString": [P, W.LPCWSTR, C.c_int, P, C.POINTER(RectF), P, P],
    "GdipAddPathString": [P,W.LPCWSTR,C.c_int,P,C.c_int,F,C.POINTER(RectF),P],
    "GdipGetPathWorldBounds": [P,C.POINTER(RectF),P,P],
    "GdipDrawImageRectI": [P, P, C.c_int, C.c_int, C.c_int, C.c_int],
    "GdipBitmapLockBits": [P, C.POINTER(RectI), W.UINT, C.c_int, C.POINTER(BitmapData)],
    "GdipBitmapUnlockBits": [P, C.POINTER(BitmapData)],
}.items():
    bind(name, args)

for name in ("GdipDeleteGraphics", "GdipDisposeImage", "GdipDeleteBrush", "GdipDeletePen",
             "GdipDeletePath", "GdipDeleteFont", "GdipDeleteFontFamily", "GdipDeleteStringFormat"):
    bind(name, [P])

token = C.c_size_t()
call("GdiplusStartup", C.byref(token), C.byref(StartupInput(1, None, False, False)), None)
api.GdiplusShutdown.argtypes = [C.c_size_t]
api.GdiplusShutdown.restype = None
atexit.register(lambda: api.GdiplusShutdown(token))


def color(value):
    value = theme.color(value)
    value = value.lstrip("#")
    return (0xff000000 if len(value) == 6 else 0) | int(value, 16)


class Renderer:
    def __init__(self, width, scale, height=None):
        self.scale, self.width = scale, width
        self.height = round(HEIGHT * scale) if height is None else height
        self.samples = 3
        self.text_runs = []
        self.text_tops = {}
        self.resources = []
        self.brushes, self.pens, self.fonts = {}, {}, {}
        self.bitmap = self.new("GdipCreateBitmapFromScan0", "GdipDisposeImage", width*self.samples, self.height*self.samples, 0, ARGB, None)
        self.g = self.new("GdipGetImageGraphicsContext", "GdipDeleteGraphics", self.bitmap)
        call("GdipGraphicsClear", self.g, 0)
        call("GdipSetSmoothingMode", self.g, 4)
        call("GdipSetTextRenderingHint", self.g, 3)
        call("GdipScaleWorldTransform", self.g, scale*self.samples, scale*self.samples, 0)
        self.family = self.new("GdipCreateFontFamilyFromName", "GdipDeleteFontFamily", ui_font_family(), None)
        self.format = self.new("GdipStringFormatGetGenericTypographic", "GdipDeleteStringFormat")
        call("GdipSetStringFormatFlags", self.format, 0x1800)
        ascent, descent = self.font_metrics(16)
        self.baseline = (HEIGHT-ascent-descent)/2+ascent
        self.diagnostics = []

    def new(self, name, cleanup, *args):
        pointer = P()
        call(name, *args, C.byref(pointer))
        self.resources.append((cleanup, pointer))
        return pointer

    def close(self):
        for name, pointer in reversed(self.resources):
            getattr(api, name)(pointer)
        self.resources.clear()

    def brush(self, ink):
        if ink not in self.brushes:
            self.brushes[ink] = self.new("GdipCreateSolidFill", "GdipDeleteBrush", color(ink))
        return self.brushes[ink]

    def pen(self, ink, thickness=1):
        key = (ink, thickness)
        if key not in self.pens:
            # World units follow the vector/DPI supersampling transform. Pixel
            # pens stayed 1 px on the 3x canvas and became hairlines on export.
            self.pens[key] = self.new("GdipCreatePen1", "GdipDeletePen", color(ink), thickness, 0)
        return self.pens[key]

    def font(self, role):
        if role not in self.fonts:
            self.fonts[role] = self.new("GdipCreateFont", "GdipDeleteFont", self.family, 14 if role == "label" else 16,
                                        1 if role in ("speed","status","value","brand") else 0, 2)
        return self.fonts[role]

    def font_metrics(self, size, bold=0):
        ascent, descent, em = W.WORD(), W.WORD(), W.WORD()
        for name, value in (("GdipGetCellAscent", ascent), ("GdipGetCellDescent", descent), ("GdipGetEmHeight", em)):
            call(name, self.family, bold, C.byref(value))
        return size*ascent.value/em.value, size*descent.value/em.value

    def measure(self, run):
        bounds = RectF()
        call("GdipMeasureString", self.g, run.text, -1, self.font(run.role), C.byref(RectF(0, 0, 10000, 100)), self.format,
             C.byref(bounds), None, None)
        return bounds.width

    def text(self, x, run, baseline=None):
        self.text_runs.append((x, run, self.baseline if baseline is None else baseline))

    def text_top(self,role):
        if role not in self.text_tops:
            # Stable optical centering by role, independent of the current
            # number's glyphs. Font em/ascent boxes are not visible ink bounds.
            sample = "Token 缓存 上下文 轮 次" if role == "label" else "生成中" if role == "status" else "Pulse" if role == "brand" else "0123456789"
            path = self.new("GdipCreatePath","GdipDeletePath",0)
            size = 14 if role == "label" else 16
            weight = 1 if role in ("speed","status","value","brand") else 0
            call("GdipAddPathString",path,sample,-1,self.family,weight,size,C.byref(RectF(0,0,1000,100)),self.format)
            bounds=RectF()
            call("GdipGetPathWorldBounds",path,C.byref(bounds),None,None)
            self.text_tops[role]=(HEIGHT-bounds.height)/2-bounds.y
        return self.text_tops[role]

    def svg(self, name, x, y, width, height):
        from svg_art import paint
        paint(self, name, x, y, width, height)

    def rounded(self, x, y, width, height, radius, fill, border=None):
        path = self.new("GdipCreatePath", "GdipDeletePath", 0)
        d = radius*2
        for px, py, angle in ((x,y,180),(x+width-d,y,270),(x+width-d,y+height-d,0),(x,y+height-d,90)):
            call("GdipAddPathArc", path, px, py, d, d, angle, 90)
        call("GdipClosePathFigure", path)
        call("GdipFillPath", self.g, self.brush(fill), path)
        if border:
            call("GdipDrawPath", self.g, self.pen(border), path)

    def line(self, x1, y1, x2, y2, ink, thickness=1):
        call("GdipDrawLine", self.g, self.pen(ink, thickness), x1, y1, x2, y2)

    def ellipse(self, x, y, w, h, ink, fill=False, thickness=1.2):
        call("GdipFillEllipse" if fill else "GdipDrawEllipse", self.g,
             self.brush(ink) if fill else self.pen(ink, thickness), x,y,w,h)

    def arc(self, x,y,w,h,start,sweep,ink,thickness=1.2):
        call("GdipDrawArc", self.g, self.pen(ink, thickness), x,y,w,h,start,sweep)

    def icon(self, key, x, progress):
        y, ink = HEIGHT/2, "#686e91"
        if key in ("rounds", "speed", "tokens", "cache", "context"):
            from svg_art import paint
            paint(self,key+".svg",x-12,y-12,24,24,
                  {"#8952ee":METRIC_INK,"#72799c":METRIC_INK})
            return
        else:
            self.ellipse(x-8,y-8,16,16,"#9298b2",thickness=1.5)
            if progress is not None and progress > 0:
                self.arc(x-8,y-8,16,16,270,min(100,progress)*3.6,ink,1.6)

    def draw(self, snapshot, hovered=False):
        width = self.width/self.scale
        self.svg("shadow.svg", 0, 0, width, HEIGHT)
        self.svg("glass-frosted.svg" if snapshot and snapshot.get("backdrop") else "glass.svg", 4, 4, width-8, ROW_HEIGHT)
        if snapshot and snapshot.get("capsule"):
            available = snapshot.get("available")
            value = "生成中" if snapshot.get("request_pending") else (
                f"≈ {snapshot['latest_tps_estimate']:.1f}" if available and snapshot.get("latest_tps_estimate") is not None else "待命")
            self.svg("wave.svg",38,HEIGHT/2-12,24,24)
            self.text(70, type("Run", (), {"text":"Pulse", "role":"brand", "gap":5})())
            self.text(123, type("Run", (), {"text":"· "+value, "role":"label", "gap":0})())
            cells = []
        else:
            cells = None
        data = metrics(snapshot)
        text_inset = CELL_PADDING+ICON_SIZE+ICON_GAP
        minimums = {key: sum(self.measure(run)+run.gap for run in metric.runs)-metric.runs[-1].gap+text_inset+CELL_TRAILING
                    for key,metric in data.items()}
        cells = columns(width, minimums, tuple(data)) if cells is None else cells
        for index, cell in enumerate(cells):
            metric = data[cell.key]
            if cell.key == "speed" and snapshot and snapshot.get("request_pending"):
                run = type("Run", (), {"text":"生成中", "role":"status", "gap":0})()
                group_width = 28+self.measure(run)
                x = cell.x+(cell.width-group_width)/2
                phase = snapshot.get("activity_phase",2)
                for dot in range(3):
                    ink = "#8771d8" if dot == phase else "#c8bee9"
                    self.ellipse(x+dot*6,HEIGHT/2-1.5,3,3,ink,True)
                x += 28
                self.text(x,run)
                x += self.measure(run)
                end = x
            else:
                self.icon(cell.key, cell.x+CELL_PADDING+ICON_SIZE/2, metric.progress)
                x = cell.x+text_inset
                for run in metric.runs:
                    self.text(x, run)
                    x += self.measure(run)+run.gap
                end = x-metric.runs[-1].gap
            self.diagnostics.append({"key":cell.key,"left":cell.x,"right":cell.x+cell.width,
                                     "icon_left":cell.x+CELL_PADDING,"text_left":cell.x+text_inset,
                                     "text_right":end,"baseline":self.baseline})
            if index < len(cells)-1:
                self.line(cell.x+cell.width,HEIGHT/2-9,cell.x+cell.width,HEIGHT/2+9,"#c9c4e6")
        for dx in (-2.5,2.5):
            for dy in (-5,0,5):
                self.ellipse(22+dx-1.25,HEIGHT/2+dy-1.25,2.5,2.5,"#797199" if hovered else "#a09ab9",True)
        self.svg("ellipsis.svg",width-34,HEIGHT/2-12,24,24)

    def png(self):
        bitmap = self.new("GdipCreateBitmapFromScan0", "GdipDisposeImage", self.width,self.height,0,ARGB,None)
        graphics = self.new("GdipGetImageGraphicsContext", "GdipDeleteGraphics", bitmap)
        call("GdipGraphicsClear",graphics,0)
        call("GdipSetInterpolationMode",graphics,7)
        call("GdipSetPixelOffsetMode",graphics,4)
        call("GdipDrawImageRectI",graphics,self.bitmap,0,0,self.width,self.height)
        # Only vector shapes are supersampled. Live glyphs are hinted once at
        # the final screen pixel size, never reduced along with a preview image.
        call("GdipSetTextRenderingHint", graphics, 3)
        call("GdipScaleWorldTransform", graphics, self.scale, self.scale, 0)
        for x, run, baseline in self.text_runs:
            ink = METRIC_INK if run.text.strip()=="—" or run.role=="label" else "#8653ec" if run.role in ("speed","status") else "#181637"
            px = round(x*self.scale)/self.scale
            top = round(self.text_top(run.role)*self.scale)/self.scale
            call("GdipDrawString", graphics, run.text, -1, self.font(run.role),
                 C.byref(RectF(px, top, 10000, 100)), self.format, self.brush(ink))
        bits = BitmapData()
        call("GdipBitmapLockBits",bitmap,C.byref(RectI(0,0,self.width,self.height)),1,ARGB,C.byref(bits))
        try:
            rows = bytearray()
            for y in range(self.height):
                bgra = C.string_at(bits.scan+y*bits.stride,self.width*4)
                rgb = bytearray(self.width*4)
                rgb[0::4], rgb[1::4], rgb[2::4], rgb[3::4] = bgra[2::4],bgra[1::4],bgra[0::4],bgra[3::4]
                rows.append(0)
                rows.extend(rgb)
        finally:
            call("GdipBitmapUnlockBits",bitmap,C.byref(bits))
        def chunk(kind,value):
            return struct.pack(">I",len(value))+kind+value+struct.pack(">I",zlib.crc32(kind+value)&0xffffffff)
        return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",self.width,self.height,8,6,0,0,0))
                +chunk(b"IDAT",zlib.compress(rows))+chunk(b"IEND",b""))


def render(snapshot, width, scale=1, hovered=False):
    renderer = Renderer(width, scale)
    try:
        renderer.draw(snapshot,hovered)
        return renderer.png(), renderer.diagnostics
    finally:
        renderer.close()
