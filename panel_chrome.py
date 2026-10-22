"""DWM rounded corners and a native shadow on our non-layered settings window."""
import ctypes as C
from ctypes import wintypes as W
import os
import native_windows as win

Procedure=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
call_previous=win.user32.CallWindowProcW
call_previous.argtypes,call_previous.restype=[C.c_void_p,W.HWND,W.UINT,W.WPARAM,W.LPARAM],C.c_ssize_t


class Chrome:
    def __init__(self,hwnd):
        pid=W.DWORD()
        win.user32.GetWindowThreadProcessId(hwnd,C.byref(pid))
        if pid.value != os.getpid():raise ValueError('Settings chrome must belong to this process')
        self.hwnd=hwnd
        self.previous=win.get_long(hwnd,-4)
        self.procedure=Procedure(self.handle)
        win.set_long(hwnd,-4,C.cast(self.procedure,C.c_void_p).value)
        # The non-client frame lets DWM own smooth corners and elevation. Its
        # layout is removed below so it adds no caption or resize border.
        win.set_long(hwnd,-16,win.get_long(hwnd,-16)|0x00c40000)
        self.rounded=False
        try:
            dwm=C.WinDLL('dwmapi')
            dwm.DwmSetWindowAttribute.argtypes=[W.HWND,W.DWORD,C.c_void_p,W.DWORD]
            dwm.DwmSetWindowAttribute.restype=C.c_long
            corner=C.c_int(2)
            self.rounded=dwm.DwmSetWindowAttribute(hwnd,33,C.byref(corner),4)==0
            margins=(C.c_int*4)(1,1,1,1)
            dwm.DwmExtendFrameIntoClientArea.argtypes=[W.HWND,C.POINTER(C.c_int*4)]
            dwm.DwmExtendFrameIntoClientArea(hwnd,C.byref(margins))
        except (OSError,AttributeError):pass
        win.user32.SetWindowPos(hwnd,None,0,0,0,0,0x37)

    def handle(self,hwnd,message,wparam,lparam):
        if message==0x83 and wparam: return 0  # WM_NCCALCSIZE
        return call_previous(self.previous,hwnd,message,wparam,lparam)

    def close(self):
        if self.hwnd and win.user32.IsWindow(self.hwnd):
            win.set_long(self.hwnd,-4,self.previous)
        self.hwnd=None
