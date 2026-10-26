"""Busca las ventanas abiertas de Windows para que Nyx pueda sentarse encima."""
import ctypes
import os
from ctypes import wintypes

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
GA_ROOT = 2
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TRANSPARENT = 0x80, 0x08000000, 0x20
IGNORED_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.restype = wintypes.HWND


def _rect(hwnd):
    """Rectángulo visible de la ventana (sin los bordes invisibles de Windows 10/11)."""
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def _is_candidate(hwnd, my_pid):
    if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return False
    cloaked = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    if cloaked.value:
        return False                         # ventanas de otros escritorios virtuales, etc.
    if user32.GetWindowTextLengthW(hwnd) == 0:
        return False
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex_style & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT):
        return False                         # capas transparentes (NVIDIA, etc.) y ventanitas de herramientas
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, cls, 64)
    if cls.value in IGNORED_CLASSES:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value != my_pid


def _edge_visible(hwnd, x, top):
    """¿Se ve el borde de arriba en ese punto, o lo tapa otra ventana?"""
    hit = user32.WindowFromPoint(wintypes.POINT(int(x), int(top) + 3))
    if not hit:
        return False
    root = user32.GetAncestor(hit, GA_ROOT)
    if root == hwnd:
        return True
    # Si lo que hay encima es la propia Nyx (o su bocadillo/chat), no cuenta como tapado
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(root, ctypes.byref(pid))
    return pid.value == os.getpid()


def visible_windows():
    """Lista de (hwnd, (left, top, right, bottom)) en píxeles físicos, de delante a atrás."""
    my_pid = os.getpid()
    found = []

    def callback(hwnd, _):
        if _is_candidate(hwnd, my_pid):
            l, t, r, b = _rect(hwnd)
            if r - l > 120 and b - t > 60:
                found.append((hwnd, (l, t, r, b)))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found


def ledge_below(x, y_from, y_to):
    """Primera ventana cuyo borde de arriba esté entre y_from y y_to en la columna x."""
    best = None
    for hwnd, (l, t, r, b) in visible_windows():
        if l + 10 <= x <= r - 10 and y_from <= t <= y_to and _edge_visible(hwnd, x, t):
            if best is None or t < best[1]:
                best = (hwnd, t)
    return best


def ledges(min_top=60):
    """Bordes de arriba donde se puede sentar: [(hwnd, rect, [x visibles])], en píxeles físicos."""
    out = []
    for hwnd, (l, t, r, b) in visible_windows():
        if t < min_top or r - l < 220:
            continue
        xs = [x for x in range(l + 70, r - 70, 40) if _edge_visible(hwnd, x, t)]
        if xs:
            out.append((hwnd, (l, t, r, b), xs))
    return out


def window_rect(hwnd):
    """Rectángulo actual de la ventana, o None si se ha cerrado o minimizado."""
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None
    return _rect(hwnd)
