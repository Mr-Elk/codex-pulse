"""One installed, complete CJK family for native widgets and GDI+ text."""
import ctypes as C
from ctypes import wintypes as W
from functools import lru_cache


class LogFont(C.Structure):
    _fields_=[('height',W.LONG),('width',W.LONG),('escapement',W.LONG),('orientation',W.LONG),('weight',W.LONG),
              ('italic',W.BYTE),('underline',W.BYTE),('strikeout',W.BYTE),('charset',W.BYTE),
              ('out_precision',W.BYTE),('clip_precision',W.BYTE),('quality',W.BYTE),('pitch',W.BYTE),('face',W.WCHAR*32)]


@lru_cache(maxsize=1)
def family():
    user,gdi=C.WinDLL('user32'),C.WinDLL('gdi32')
    user.GetDC.argtypes,user.GetDC.restype=[W.HWND],W.HDC
    user.ReleaseDC.argtypes=[W.HWND,W.HDC]
    callback=C.WINFUNCTYPE(C.c_int,C.POINTER(LogFont),C.c_void_p,W.DWORD,W.LPARAM)
    gdi.EnumFontFamiliesExW.argtypes=[W.HDC,C.POINTER(LogFont),callback,W.LPARAM,W.DWORD]
    names={}
    @callback
    def collect(font,*_):
        name=font.contents.face
        if not name.startswith('@'):names[name.casefold()]=name
        return 1
    dc=user.GetDC(None)
    try:gdi.EnumFontFamiliesExW(dc,C.byref(LogFont(charset=1)),collect,0,0)
    finally:user.ReleaseDC(None,dc)
    for name in ('Alibaba PuHuiTi 3.0','Alibaba PuHuiTi 2.0','Alibaba PuHuiTi','阿里巴巴普惠体 3.0',
                 '阿里巴巴普惠体','Noto Sans SC','等线','DengXian','Microsoft JhengHei UI'):
        if name.casefold() in names:return names[name.casefold()]
    raise RuntimeError('No supported complete CJK UI font is installed')
