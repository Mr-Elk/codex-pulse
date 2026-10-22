"""Keep Tk's default paints away from our own per-pixel foreground pixels."""
import ctypes as C
from ctypes import wintypes as W

user=C.WinDLL("user32",use_last_error=True)
controls=C.WinDLL("comctl32",use_last_error=True)
Procedure=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM,C.c_size_t,C.c_size_t)
controls.SetWindowSubclass.argtypes=[W.HWND,Procedure,C.c_size_t,C.c_size_t]
controls.SetWindowSubclass.restype=W.BOOL
controls.RemoveWindowSubclass.argtypes=[W.HWND,Procedure,C.c_size_t]
controls.RemoveWindowSubclass.restype=W.BOOL
controls.DefSubclassProc.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
controls.DefSubclassProc.restype=C.c_ssize_t
user.ValidateRect.argtypes=[W.HWND,C.c_void_p]
user.ValidateRect.restype=W.BOOL


class PaintGuard:
    """Subclass only our toolbar HWNDs; settings and input dispatch are untouched."""
    def __init__(self,handles,ready):
        self.ready=ready;self.handles=set();self.suppressed=0;self.reason=None
        self.identity=id(self)
        self.procedure=Procedure(self.dispatch)
        for handle in set(handles):
            if handle and controls.SetWindowSubclass(handle,self.procedure,self.identity,0):
                self.handles.add(handle)
            elif handle:
                self.reason="foreground_subclass_unavailable"

    def dispatch(self,hwnd,message,wparam,lparam,*_):
        if message in (0x0f,0x14) and self.ready():  # WM_PAINT / WM_ERASEBKGND
            self.suppressed+=1
            if message==0x0f:
                user.ValidateRect(hwnd,None)
                return 0
            return 1
        if message==0x82:  # WM_NCDESTROY; never retain a callback on a dead HWND.
            controls.RemoveWindowSubclass(hwnd,self.procedure,self.identity)
            self.handles.discard(hwnd)
        return controls.DefSubclassProc(hwnd,message,wparam,lparam)

    def close(self):
        for handle in tuple(self.handles):
            controls.RemoveWindowSubclass(handle,self.procedure,self.identity)
        self.handles.clear()
