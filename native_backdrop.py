"""A rounded, input-transparent native blur host behind our RGBA foreground.

No screenshot of the user's content is copied into Python. Windows composes
and clips the backdrop. Unsupported systems retain the translucent SVG surface.
"""
import ctypes as C
from ctypes import wintypes as W
import winreg
from pathlib import Path
import native_windows as win
from overlay_style import HEIGHT

user=win.user32
gdi=C.WinDLL('gdi32',use_last_error=True)
Procedure=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
user.DefWindowProcW.argtypes,user.DefWindowProcW.restype=[W.HWND,W.UINT,W.WPARAM,W.LPARAM],C.c_ssize_t


@Procedure
def window_proc(hwnd,message,wparam,lparam):
    if message==0x14:return 1
    if message==0x84:return -1
    return user.DefWindowProcW(hwnd,message,wparam,lparam)


class WindowClass(C.Structure):
    _fields_=[('style',W.UINT),('proc',Procedure),('class_extra',C.c_int),('window_extra',C.c_int),
              ('instance',W.HINSTANCE),('icon',W.HICON),('cursor',W.HANDLE),('brush',W.HBRUSH),
              ('menu',W.LPCWSTR),('name',W.LPCWSTR)]


win.kernel32.GetModuleHandleW.argtypes,win.kernel32.GetModuleHandleW.restype=[W.LPCWSTR],W.HMODULE
cls=WindowClass(proc=window_proc,instance=win.kernel32.GetModuleHandleW(None),name='CodexPulseBlurV2')
user.RegisterClassW.argtypes=[C.POINTER(WindowClass)]
user.RegisterClassW(C.byref(cls))
user.CreateWindowExW.argtypes=[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p]
user.CreateWindowExW.restype=W.HWND
user.DestroyWindow.argtypes=[W.HWND]


class Backdrop:
    def __init__(self,owner=None):
        self.hwnd=None;self.available=False;self.visible=False;self.last_rect=None;self.size=None
        self.instance=C.c_void_p();self.library=None
        self.reason=None;self.shows=0;self.hides=0;self.moves=0
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                if winreg.QueryValueEx(key,'EnableTransparency')[0]==0:
                    self.reason='transparency_disabled';return
        except OSError:pass
        try:
            self.library=C.WinDLL(str(Path(__file__).parent/'assets'/'native'/'pulse_backdrop_x64.dll'))
            self.library.pulse_blur_create.argtypes=[W.HWND,C.POINTER(C.c_void_p)]
            self.library.pulse_blur_create.restype=C.c_long
            self.library.pulse_blur_resize.argtypes=[C.c_void_p,C.c_float,C.c_float]
            self.library.pulse_blur_resize.restype=C.c_long
            self.library.pulse_blur_destroy.argtypes=[C.c_void_p]
            self.hwnd=user.CreateWindowExW(0x80|0x08000000|0x20|0x00200000,cls.name,'',0x80000000,0,0,1,1,owner,None,cls.instance,None)
            if not self.hwnd:raise C.WinError(C.get_last_error())
            result=self.library.pulse_blur_create(self.hwnd,C.byref(self.instance))
            self.available=result>=0 and bool(self.instance)
            if not self.available:self.reason=f'composition_unavailable_{result & 0xffffffff:08x}'
        except (OSError,AttributeError) as error:
            self.reason=type(error).__name__

    def place(self,foreground,rect,shown,*,force=False):
        if not self.available or not shown:
            if self.visible:
                win.hide(self.hwnd);self.hides+=1
            self.visible=False;self.last_rect=None
            return
        same = self.visible and self.last_rect==rect
        if same and not force:return
        scale=rect.height/HEIGHT
        inset=max(1,round(5.5*scale))
        left,top=rect.left+inset,rect.top+inset
        width,height=max(1,rect.width-2*inset),max(1,rect.height-2*inset)
        if (width,height)!=self.size:
            if self.library.pulse_blur_resize(self.instance,width,height)<0:
                self.available=False;self.reason='rounded_clip_unavailable'
                self.place(foreground,rect,False)
                return
            self.size=(width,height)
        flags=0x10|0x40|0x200|(0x3 if same else 0)
        if not user.SetWindowPos(self.hwnd,W.HWND(foreground),left,top,width,height,flags):
            self.available=False;self.reason='blur_placement_failed'
            self.place(foreground,rect,False)
            return
        self.moves+=int(not same)
        if not self.visible:self.shows+=1
        self.visible=True;self.last_rect=rect

    def close(self):
        if self.instance and self.library:self.library.pulse_blur_destroy(self.instance)
        self.instance=C.c_void_p()
        if self.hwnd:user.DestroyWindow(self.hwnd)
        self.hwnd=None;self.visible=False
