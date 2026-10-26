"""DWM rounded corners and a native shadow on our non-layered settings window."""
import ctypes as C
from ctypes import wintypes as W
import os
import native_windows as win

Procedure=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
call_previous=win.user32.CallWindowProcW
call_previous.argtypes,call_previous.restype=[C.c_void_p,W.HWND,W.UINT,W.WPARAM,W.LPARAM],C.c_ssize_t


class Chrome:
    def __init__(self,hwnd,framed=True):
        pid=W.DWORD()
        win.user32.GetWindowThreadProcessId(hwnd,C.byref(pid))
        if pid.value != os.getpid():raise ValueError('Settings chrome must belong to this process')
        self.hwnd=hwnd
        self.previous=win.get_long(hwnd,-4)
        self.procedure=Procedure(self.handle)
        win.set_long(hwnd,-4,C.cast(self.procedure,C.c_void_p).value)
        # The non-client frame lets DWM own smooth corners and elevation. Its
        # layout is removed below so it adds no caption or resize border.
        style=win.get_long(hwnd,-16)
        # A custom rounded region must stay captionless; otherwise Windows
        # falls back to painting a thick native frame when focus returns.
        win.set_long(hwnd,-16,style|0x00c40000 if framed else style & ~0x00c40000)
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


class RoundedRegion:
    """Clip an app-owned native surface to the design radius on every resize."""
    def __init__(self,window,scale,radius):
        self.window,self.scale,self.radius,self.signature=window,scale,radius,None
        self.hwnd=win.top_level(window.winfo_id())
        window.bind('<Configure>',self.resize,add='+')
    def resize(self,event=None):
        if event is not None and event.widget is not self.window:return
        width,height=self.window.winfo_width(),self.window.winfo_height()
        signature=(width,height,self.scale)
        if width<2 or height<2 or signature==self.signature:return
        self.signature=signature
        gdi=C.WinDLL('gdi32',use_last_error=True)
        gdi.CreateRoundRectRgn.argtypes=[C.c_int]*6;gdi.CreateRoundRectRgn.restype=W.HRGN
        gdi.DeleteObject.argtypes=[W.HGDIOBJ]
        win.user32.SetWindowRgn.argtypes=[W.HWND,W.HRGN,W.BOOL];win.user32.SetWindowRgn.restype=C.c_int
        diameter=round(self.radius*self.scale)*2
        region=gdi.CreateRoundRectRgn(0,0,width+1,height+1,diameter,diameter)
        if region and not win.user32.SetWindowRgn(self.hwnd,region,True):gdi.DeleteObject(region)

class PopupCard(RoundedRegion):
    """One rounded, bordered surface for our own menus, dialogs and details."""
    def __init__(self,window,scale,padx=20,pady=20):
        from panel_widgets import Surface
        super().__init__(window,scale,12)
        self.chrome=Chrome(self.hwnd,framed=False)
        self.surface=Surface(window,scale,fill='#ffffff',padx=padx,pady=pady)
        self.surface.pack(fill='both',expand=True)
        self.body=self.surface.inner
        window.bind('<Destroy>',self.destroy,add='+')
    def destroy(self,event):
        if event.widget is self.window:self.close()
    def close(self):
        self.chrome.close()
