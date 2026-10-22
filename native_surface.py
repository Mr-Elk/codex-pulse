"""Per-pixel foreground over a clipped compositor backdrop; no pixel readback."""
import ctypes as C
from ctypes import wintypes as W
import struct
import zlib
import time

import native_windows as win

user, gdi = win.user32, C.WinDLL("gdi32", use_last_error=True)


class Header(C.Structure):
    _fields_ = [("size",W.DWORD),("width",W.LONG),("height",W.LONG),("planes",W.WORD),
                ("bits",W.WORD),("compression",W.DWORD),("image_size",W.DWORD),
                ("x",W.LONG),("y",W.LONG),("used",W.DWORD),("important",W.DWORD)]


class Blend(C.Structure):
    _fields_ = [("operation",W.BYTE),("flags",W.BYTE),("alpha",W.BYTE),("format",W.BYTE)]


gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = [W.HDC], W.HDC
gdi.CreateDIBSection.argtypes = [W.HDC,C.POINTER(Header),W.UINT,C.POINTER(C.c_void_p),W.HANDLE,W.DWORD]
gdi.CreateDIBSection.restype = W.HBITMAP
gdi.SelectObject.argtypes, gdi.SelectObject.restype = [W.HDC,W.HGDIOBJ], W.HGDIOBJ
gdi.DeleteObject.argtypes, gdi.DeleteDC.argtypes = [W.HGDIOBJ], [W.HDC]
user.UpdateLayeredWindow.argtypes = [W.HWND,W.HDC,C.POINTER(W.POINT),C.POINTER(W.SIZE),W.HDC,
                                    C.POINTER(W.POINT),W.DWORD,C.POINTER(Blend),W.DWORD]
user.UpdateLayeredWindow.restype = W.BOOL
user.CreateWindowExW.argtypes = [W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,
                                W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p]
user.CreateWindowExW.restype = W.HWND
user.DestroyWindow.argtypes = [W.HWND]
user.SetWindowRgn.argtypes = [W.HWND,W.HRGN,W.BOOL]
gdi.CreateRoundRectRgn.argtypes = [C.c_int]*6
gdi.CreateRoundRectRgn.restype = W.HRGN

def rgba_pixels(png):
    """Decode only our renderer's unfiltered RGBA PNG, not arbitrary image files."""
    offset, packed, size = 8, bytearray(), None
    while offset < len(png):
        count = struct.unpack(">I",png[offset:offset+4])[0]
        kind, data = png[offset+4:offset+8], png[offset+8:offset+8+count]
        if kind == b"IHDR":
            width,height,bits,color,*_ = struct.unpack(">IIBBBBB",data)
            if bits != 8 or color != 6 or width > 10000 or height > 2000:
                raise ValueError("Expected our RGBA strip")
            size = width,height
        elif kind == b"IDAT":
            packed.extend(data)
        offset += count+12
    if size is None:
        raise ValueError("Missing image size")
    width,height = size
    rows = zlib.decompress(packed)
    stride = width*4+1
    if len(rows) != stride*height or any(rows[y*stride] for y in range(height)):
        raise ValueError("Expected unfiltered renderer pixels")
    rgba = b"".join(rows[y*stride+1:(y+1)*stride] for y in range(height))
    bgra = bytearray(len(rgba))
    for i in range(0,len(rgba),4):
        r,g,b,a = rgba[i:i+4]
        bgra[i:i+4] = bytes(((b*a+127)//255,(g*a+127)//255,(r*a+127)//255,a))
    return width,height,bgra


class Surface:
    def __init__(self, hwnd, owner=None, input_hwnd=None):
        self.hwnd = hwnd
        self.dc = gdi.CreateCompatibleDC(None)
        self.bitmap = self.previous = self.bits = None
        self.size = None
        self.shown = False
        self.last_frame = None
        self.last_upload = 0
        self.last_repair = 0
        self.uploads = self.repairs = 0
        self.last_error = None
        from native_backdrop import Backdrop
        self.material = Backdrop(owner)
        # Reset SLA state once before per-pixel updates. Later passthrough changes
        # must not call SetLayeredWindowAttributes and invalidate this surface.
        extended = win.get_long(hwnd,-20)
        win.set_long(hwnd,-20,extended & ~0x80000)
        win.set_long(hwnd,-20,extended | 0x80000)
        from native_foreground import PaintGuard
        self.paint_guard=PaintGuard((hwnd,input_hwnd),lambda:self.uploads>0)

    def set_image(self, png):
        width,height,pixels = rgba_pixels(png)
        if (width,height) != self.size:
            if self.bitmap:
                gdi.SelectObject(self.dc,self.previous)
                gdi.DeleteObject(self.bitmap)
            header = Header(size=C.sizeof(Header),width=width,height=-height,planes=1,bits=32)
            self.bits = C.c_void_p()
            self.bitmap = gdi.CreateDIBSection(self.dc,C.byref(header),0,C.byref(self.bits),None,0)
            if not self.bitmap:
                raise C.WinError(C.get_last_error())
            self.previous = gdi.SelectObject(self.dc,self.bitmap)
            self.size = width,height
        C.memmove(self.bits,bytes(pixels),len(pixels))
        self.last_frame = None

    def invalidate(self):
        self.last_frame = None
        self.last_repair = 0

    def present(self, rect, alpha=255):
        if self.size is None:
            return
        if not alpha:
            self.hide()
            return
        frame = (rect,alpha)
        now = time.monotonic()
        actually_visible = bool(user.IsWindowVisible(self.hwnd))
        repair = not actually_visible or now-self.last_repair>=1
        if frame == self.last_frame and not repair:
            return
        point, source = W.POINT(rect.left,rect.top), W.POINT(0,0)
        size, blend = W.SIZE(*self.size), Blend(0,0,alpha,1)
        if not user.UpdateLayeredWindow(self.hwnd,None,C.byref(point),C.byref(size),self.dc,
                                       C.byref(source),0,C.byref(blend),2):
            # A transient graphics failure must not stop Tk's scheduling loop.
            # Keep the last surface visible and retry without a hide/show reset.
            self.last_error = f"UpdateLayeredWindow:{C.get_last_error()}"
            self.last_frame = None
            return
        self.last_upload = now
        self.uploads += 1
        self.repairs += int(repair)
        if repair:
            self.last_repair = now
        self.last_error = None
        if not self.shown or not actually_visible:
            user.ShowWindow(self.hwnd,4)
            self.shown = True
        self.material.place(self.hwnd,rect,alpha >= 250,force=repair)
        self.last_frame = frame

    def hide(self):
        if self.shown:
            win.hide(self.hwnd)
        self.shown = False
        self.material.place(self.hwnd,None,False)
        self.last_frame = None

    def close(self):
        self.hide()
        if hasattr(self,"paint_guard"):
            self.paint_guard.close()
        self.material.close()
        if self.bitmap:
            gdi.SelectObject(self.dc,self.previous)
            gdi.DeleteObject(self.bitmap)
            self.bitmap = None
        if self.dc:
            gdi.DeleteDC(self.dc)
            self.dc = None
