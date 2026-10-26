"""One installed, complete CJK family for native widgets and GDI+ text."""
import ctypes as C
from ctypes import wintypes as W
from functools import lru_cache
from pathlib import Path

PRIVATE_FAMILY='Noto Sans SC Pulse'
PRIVATE_FONTS=tuple(Path(__file__).resolve().parent/'assets'/'fonts'/('NotoSansSCPulse-'+style+'.ttf')
                    for style in ('Regular','Bold'))


@lru_cache(maxsize=1)
def private_font_buffers():
    if not all(path.is_file() for path in PRIVATE_FONTS):return ()
    return tuple(C.create_string_buffer(path.read_bytes()) for path in PRIVATE_FONTS)


@lru_cache(maxsize=1)
def load_private_fonts():
    """Expose static Noto outlines only to this process, before Tk maps fonts."""
    if not all(path.is_file() for path in PRIVATE_FONTS):return False
    gdi=C.WinDLL('gdi32')
    gdi.AddFontResourceExW.argtypes=[W.LPCWSTR,W.DWORD,C.c_void_p]
    gdi.AddFontResourceExW.restype=C.c_int
    for path in PRIVATE_FONTS:
        if not gdi.AddFontResourceExW(str(path),0x10,None):
            raise OSError('Could not load bundled Noto Sans SC font')
    return True


class LogFont(C.Structure):
    _fields_=[('height',W.LONG),('width',W.LONG),('escapement',W.LONG),('orientation',W.LONG),('weight',W.LONG),
              ('italic',W.BYTE),('underline',W.BYTE),('strikeout',W.BYTE),('charset',W.BYTE),
              ('out_precision',W.BYTE),('clip_precision',W.BYTE),('quality',W.BYTE),('pitch',W.BYTE),('face',W.WCHAR*32)]


@lru_cache(maxsize=1)
def installed_families():
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
    return names


@lru_cache(maxsize=1)
def family():
    names=installed_families()
    for name in ('Alibaba PuHuiTi 3.0','Alibaba PuHuiTi 2.0','Alibaba PuHuiTi','阿里巴巴普惠体 3.0','阿里巴巴普惠体'):
        if name.casefold() in names:return names[name.casefold()]
    if load_private_fonts():return PRIVATE_FAMILY
    for name in ('Noto Sans SC','等线','DengXian','Microsoft JhengHei UI'):
        if name.casefold() in names:return names[name.casefold()]
    raise RuntimeError('No supported complete CJK UI font is installed')


@lru_cache(maxsize=1)
def widget_family():
    """Keep native controls, popups and strip text in the agreed family."""
    return family()
