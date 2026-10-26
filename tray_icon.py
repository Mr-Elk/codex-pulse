"""App-owned Windows tray recovery; no startup, registry or system changes."""
import ctypes as C
from ctypes import wintypes as W

class Notify(C.Structure):
    _fields_=[('cbSize',W.DWORD),('hWnd',W.HWND),('uID',W.UINT),('uFlags',W.UINT),('uCallbackMessage',W.UINT),('hIcon',W.HICON),('szTip',W.WCHAR*128),('dwState',W.DWORD),('dwStateMask',W.DWORD),('szInfo',W.WCHAR*256),('uVersion',W.UINT),('szInfoTitle',W.WCHAR*64),('dwInfoFlags',W.DWORD),('guidItem',C.c_byte*16),('hBalloonIcon',W.HICON)]

class TrayIcon:
    MESSAGE=0x8000+73
    def __init__(self,owner):
        self.owner=owner;self.hwnd=owner.hwnd;self.user=C.WinDLL('user32',use_last_error=True);self.shell=C.WinDLL('shell32',use_last_error=True)
        self.user.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int];self.user.GetWindowLongPtrW.restype=C.c_ssize_t
        self.user.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,C.c_ssize_t];self.user.SetWindowLongPtrW.restype=C.c_ssize_t
        self.user.CallWindowProcW.argtypes=[C.c_void_p,W.HWND,W.UINT,W.WPARAM,W.LPARAM];self.user.CallWindowProcW.restype=C.c_ssize_t
        self.user.LoadIconW.argtypes=[W.HINSTANCE,C.c_void_p];self.user.LoadIconW.restype=W.HICON
        self.shell.Shell_NotifyIconW.argtypes=[W.DWORD,C.POINTER(Notify)];self.shell.Shell_NotifyIconW.restype=W.BOOL
        self.user.CreatePopupMenu.restype=W.HMENU;self.user.AppendMenuW.argtypes=[W.HMENU,W.UINT,C.c_size_t,W.LPCWSTR]
        self.user.TrackPopupMenu.argtypes=[W.HMENU,W.UINT,C.c_int,C.c_int,C.c_int,W.HWND,C.c_void_p];self.user.TrackPopupMenu.restype=W.UINT
        self.user.DestroyMenu.argtypes=[W.HMENU]
        self.user.DestroyIcon.argtypes=[W.HICON];self.user.SetForegroundWindow.argtypes=[W.HWND]
        self.user.LoadImageW.argtypes=[W.HINSTANCE,W.LPCWSTR,W.UINT,C.c_int,C.c_int,W.UINT];self.user.LoadImageW.restype=W.HICON
        icon_path=__import__('pathlib').Path(__file__).with_name('assets')/'pulse.ico'
        self.icon=self.user.LoadImageW(None,str(icon_path),1,32,32,0x10) if icon_path.exists() else None
        self.owns_icon=bool(self.icon);self.icon=self.icon or self.user.LoadIconW(None,C.c_void_p(32512))
        self.data=Notify();self.data.cbSize=C.sizeof(Notify);self.data.hWnd=self.hwnd;self.data.uID=19;self.data.uFlags=1|2|4;self.data.uCallbackMessage=self.MESSAGE;self.data.hIcon=self.icon;self.data.szTip='Codex Pulse · 点击打开设置'
        self.previous=self.user.GetWindowLongPtrW(self.hwnd,-4);prototype=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
        def proc(hwnd,msg,wparam,lparam):
            if msg==self.MESSAGE:
                if lparam==0x202:owner.root.after_idle(owner.open_settings)
                elif lparam==0x205:self.menu()
                return 0
            return self.user.CallWindowProcW(C.c_void_p(self.previous),hwnd,msg,wparam,lparam)
        self.proc=prototype(proc);self.pointer=C.cast(self.proc,C.c_void_p).value;self.user.SetWindowLongPtrW(self.hwnd,-4,self.pointer)
        self.available=bool(self.shell.Shell_NotifyIconW(0,C.byref(self.data)))
    def menu(self):
        menu=self.user.CreatePopupMenu();commands=[('显示统计条',self.restore),('打开设置',self.owner.open_settings),('恢复位置',self.owner.reset_position),('退出',self.owner.close)]
        for index,(title,_) in enumerate(commands,1):self.user.AppendMenuW(menu,0,index,title)
        point=W.POINT();self.user.GetCursorPos(C.byref(point));self.user.SetForegroundWindow(self.hwnd)
        choice=self.user.TrackPopupMenu(menu,0x0100|0x0002,point.x,point.y,0,self.hwnd,None);self.user.DestroyMenu(menu)
        if choice:self.owner.root.after_idle(commands[choice-1][1])
    def restore(self):self.owner.strip_visible=True;self.owner.save_preferences();self.owner.update_freshness()
    def close(self):
        self.shell.Shell_NotifyIconW(2,C.byref(self.data))
        if self.user.GetWindowLongPtrW(self.hwnd,-4)==self.pointer:self.user.SetWindowLongPtrW(self.hwnd,-4,self.previous)
        if self.owns_icon:self.user.DestroyIcon(self.icon)
