"""Windows metadata and positioning for our own overlay; no input injection."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import PureWindowsPath

user32 = C.WinDLL("user32", use_last_error=True)
kernel32 = C.WinDLL("kernel32", use_last_error=True)
CALLBACK = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)


class MonitorInfo(C.Structure):
    _fields_ = [("size", W.DWORD), ("monitor", W.RECT), ("work", W.RECT), ("flags", W.DWORD)]


user32.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
user32.MonitorFromWindow.restype = W.HANDLE
user32.GetMonitorInfoW.argtypes = [W.HANDLE, C.POINTER(MonitorInfo)]
user32.GetMonitorInfoW.restype = W.BOOL

user32.EnumWindows.argtypes = [CALLBACK, W.LPARAM]
user32.EnumWindows.restype = W.BOOL
user32.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
user32.GetWindowRect.restype = W.BOOL
user32.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
user32.GetClientRect.restype = W.BOOL
user32.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
user32.ClientToScreen.restype = W.BOOL
user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
user32.GetWindowThreadProcessId.restype = W.DWORD
user32.GetWindowTextLengthW.argtypes = [W.HWND]
user32.GetWindowTextLengthW.restype = C.c_int
user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
user32.GetWindowTextW.restype = C.c_int
user32.IsWindowVisible.argtypes = [W.HWND]
user32.IsWindowVisible.restype = W.BOOL
user32.IsWindow.argtypes = [W.HWND]
user32.IsWindow.restype = W.BOOL
user32.IsIconic.argtypes = [W.HWND]
user32.IsIconic.restype = W.BOOL
user32.GetForegroundWindow.restype = W.HWND
user32.SetForegroundWindow.argtypes = [W.HWND]
user32.SetForegroundWindow.restype = W.BOOL
user32.GetCursorPos.argtypes = [C.POINTER(W.POINT)]
user32.GetCursorPos.restype = W.BOOL
user32.GetAsyncKeyState.argtypes = [C.c_int]
user32.GetAsyncKeyState.restype = W.SHORT
user32.SetLayeredWindowAttributes.argtypes = [W.HWND, W.DWORD, W.BYTE, W.DWORD]
user32.SetLayeredWindowAttributes.restype = W.BOOL
user32.GetAncestor.argtypes = [W.HWND, W.UINT]
user32.GetAncestor.restype = W.HWND
user32.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
user32.SetWindowPos.restype = W.BOOL
user32.ShowWindow.argtypes = [W.HWND, C.c_int]
user32.ShowWindow.restype = W.BOOL
kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel32.OpenProcess.restype = W.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = W.BOOL
kernel32.CloseHandle.argtypes = [W.HANDLE]
kernel32.CloseHandle.restype = W.BOOL
LONG_PTR = C.c_ssize_t
get_long = user32.GetWindowLongPtrW
get_long.argtypes = [W.HWND, C.c_int]
get_long.restype = LONG_PTR
set_long = user32.SetWindowLongPtrW
set_long.argtypes = [W.HWND, C.c_int, LONG_PTR]
set_long.restype = LONG_PTR


def dpi_awareness():
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [C.c_void_p]
        user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    except (AttributeError, OSError):
        pass


def dpi(hwnd):
    try:
        user32.GetDpiForWindow.argtypes = [W.HWND]
        user32.GetDpiForWindow.restype = W.UINT
        return (user32.GetDpiForWindow(hwnd) or 96) / 96
    except AttributeError:
        return 1


def client_rect(hwnd):
    from overlay_geometry import Rect
    rect, origin = W.RECT(), W.POINT()
    if not user32.GetClientRect(hwnd, C.byref(rect)) or not user32.ClientToScreen(hwnd, C.byref(origin)):
        return None
    return Rect(origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom)


def window_metadata(hwnd, allow_minimized=False):
    """Verify one app-owned top-level handle, including an explicit minimized target."""
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
        return None
    if user32.GetAncestor(hwnd, 2) != hwnd:
        return None
    rect = client_rect(hwnd)
    if rect is None or ((rect.width < 400 or rect.height < 200) and not (allow_minimized and user32.IsIconic(hwnd))):
        return None
    pid = W.DWORD()
    user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
    process = kernel32.OpenProcess(0x1000, False, pid.value)
    if not process:
        return None
    path, length = C.create_unicode_buffer(32768), W.DWORD(32768)
    try:
        if not kernel32.QueryFullProcessImageNameW(process, 0, path, C.byref(length)):
            return None
    finally:
        kernel32.CloseHandle(process)
    name = PureWindowsPath(path.value).name.lower()
    if name not in ("codex.exe", "chatgpt.exe"):
        return None
    title = C.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
    user32.GetWindowTextW(hwnd, title, len(title))
    return {"hwnd": int(hwnd), "pid": pid.value, "app": name,
            "title": title.value, "rect": rect.__dict__}


def app_windows():
    """Only metadata for visible Codex/ChatGPT top-level windows."""
    found = []
    @CALLBACK
    def each(hwnd, _):
        item = window_metadata(hwnd)
        if item:
            found.append(item)
        return True
    user32.EnumWindows(each, 0)
    return found


def select_window(explicit=None):
    if explicit:
        return window_metadata(explicit, allow_minimized=True)
    windows = app_windows()
    foreground = user32.GetForegroundWindow()
    chosen = next((w for w in windows if w["hwnd"] == foreground), None)
    return chosen or (windows[0] if len(windows) == 1 else None)


def own_overlay(hwnd, owner):
    # Change only our helper window. An owned window stays above its app without
    # using the system-wide topmost band.
    set_long(hwnd, -8, owner or 0)


def set_floating(hwnd, enabled):
    """Only desktop mode uses the floating band; no activation or owner edits."""
    user32.SetWindowPos(hwnd, W.HWND(-1 if enabled else -2), 0, 0, 0, 0, 0x13|0x200)


def work_area(hwnd):
    """Place settings on the target monitor, including monitors left of primary."""
    from overlay_geometry import Rect
    info = MonitorInfo(size=C.sizeof(MonitorInfo))
    monitor = user32.MonitorFromWindow(hwnd, 2)
    if monitor and user32.GetMonitorInfoW(monitor, C.byref(info)):
        r = info.work
        return Rect(r.left, r.top, r.right, r.bottom)
    return None


def decorate_overlay(hwnd, owner=None):
    # Tool window, and never activate on show/click. Only our window is modified.
    set_long(hwnd, -20, get_long(hwnd, -20) | 0x80 | 0x08000000)
    # Demote before attaching an external owner: demoting an owned topmost
    # window can otherwise also change its owner's topmost state.
    user32.SetWindowPos(hwnd, W.HWND(-2), 0, 0, 0, 0, 0x13 | 0x20 | 0x200)
    own_overlay(hwnd, owner)


def show_without_focus(hwnd, rect, raise_window=False):
    # Raise only when first showing/resuming. Moving the strip must not keep
    # pushing it ahead of menus and other windows every placement tick.
    flags = 0x10 | 0x40 | 0x200 | (0 if raise_window else 0x4)
    user32.SetWindowPos(hwnd, W.HWND(0), rect.left, rect.top, rect.width, rect.height, flags)


def hide(hwnd):
    user32.ShowWindow(hwnd, 0)


def edit_modifier_down():
    # Only these two modifiers are inspected, only for our window's edit mode.
    # No key hook, character capture, input injection or key logging.
    return bool(user32.GetAsyncKeyState(0x11) & 0x8000 and user32.GetAsyncKeyState(0x12) & 0x8000)


def cursor_position():
    # A point-in-our-controls check, with no hook, recording or input injection.
    point = W.POINT()
    if user32.GetCursorPos(C.byref(point)):
        return point.x, point.y
    return None


def restore_startup_focus(hwnd, previous):
    # Tk can activate its wrapper before we apply NOACTIVATE. Restore only
    # the exact former window, and only while our own window still has focus.
    # A user switch to another app must never be overridden.
    if (previous and previous != hwnd and user32.GetForegroundWindow() == hwnd
            and user32.IsWindow(previous) and user32.IsWindowVisible(previous)
            and not user32.IsIconic(previous)):
        # Release an activation left behind by Tk's initially withdrawn wrapper.
        # Showing without activation then hiding changes only our own window.
        owner = get_long(hwnd, -8)
        try:
            if owner != previous:
                own_overlay(hwnd, previous)
            user32.ShowWindow(hwnd, 4)
            user32.ShowWindow(hwnd, 0)
        finally:
            if owner != previous:
                own_overlay(hwnd, owner)
        foreground = user32.GetForegroundWindow()
        if foreground == previous:
            return True
        if foreground == hwnd:
            return bool(user32.SetForegroundWindow(previous))
    return False


def set_passthrough(hwnd, enabled, per_pixel=False):
    extended = get_long(hwnd, -20) | 0x80000
    extended = (extended | 0x20) if enabled else (extended & ~0x20)
    set_long(hwnd, -20, extended)
    if not per_pixel and not user32.SetLayeredWindowAttributes(hwnd, 0, 255, 0x2):
        raise C.WinError(C.get_last_error())


def active_target(hwnd):
    return bool(user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd)
                and user32.GetForegroundWindow() == hwnd)


def top_level(tk_hwnd):
    return int(user32.GetAncestor(tk_hwnd, 2))
