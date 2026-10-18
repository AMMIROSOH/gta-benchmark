"""Resolve the game window and its client area for local video capture."""

import ctypes as ct
from ctypes import wintypes as wt
from dataclasses import dataclass

user = ct.WinDLL("user32", use_last_error=True)
user.GetForegroundWindow.restype = wt.HWND
user.GetWindowThreadProcessId.argtypes = [wt.HWND, ct.POINTER(wt.DWORD)]
user.IsWindowVisible.argtypes = [wt.HWND]
user.IsWindowVisible.restype = wt.BOOL
user.IsIconic.argtypes = [wt.HWND]
user.IsIconic.restype = wt.BOOL
user.GetClientRect.argtypes = [wt.HWND, ct.POINTER(wt.RECT)]
user.GetClientRect.restype = wt.BOOL
user.ClientToScreen.argtypes = [wt.HWND, ct.POINTER(wt.POINT)]
user.ClientToScreen.restype = wt.BOOL
user.SetForegroundWindow.argtypes = [wt.HWND]
user.SetForegroundWindow.restype = wt.BOOL
CALLBACK = ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user.EnumWindows.argtypes = [CALLBACK, wt.LPARAM]
user.EnumWindows.restype = wt.BOOL
user.SetProcessDpiAwarenessContext.argtypes = [ct.c_void_p]
user.SetProcessDpiAwarenessContext.restype = wt.BOOL


@dataclass(frozen=True)
class GameWindow:
    handle: int
    process_id: int

    @classmethod
    def find(cls, process_id):
        # Pixel coordinates must match Desktop Duplication rather than DPI-scaled units.
        user.SetProcessDpiAwarenessContext(ct.c_void_p(-4))
        candidates = []
        @CALLBACK
        def visit(handle, _):
            pid = wt.DWORD()
            user.GetWindowThreadProcessId(handle, ct.byref(pid))
            rect = wt.RECT()
            if (pid.value == process_id and user.IsWindowVisible(handle) and
                user.GetClientRect(handle, ct.byref(rect)) and rect.right >= 320 and rect.bottom >= 240):
                candidates.append(handle)
            return True
        user.EnumWindows(visit, 0)
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one GTA game window, found {len(candidates)}")
        return cls(candidates[0], process_id)

    def foreground(self):
        pid = wt.DWORD()
        user.GetWindowThreadProcessId(self.handle, ct.byref(pid))
        return (pid.value == self.process_id and user.GetForegroundWindow() == self.handle
                and not user.IsIconic(self.handle))

    def activate(self):
        user.SetForegroundWindow(self.handle)

    def region(self):
        rect, origin = wt.RECT(), wt.POINT(0, 0)
        if not user.GetClientRect(self.handle, ct.byref(rect)) or not user.ClientToScreen(self.handle, ct.byref(origin)):
            raise ct.WinError(ct.get_last_error())
        return origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom
