"""Atajo de teclado global de Windows (funciona aunque Nyx no tenga el foco)."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
user32 = ctypes.windll.user32


class GlobalHotkey(QAbstractNativeEventFilter):
    """Llama a `callback` cuando se pulsa Ctrl + Alt + <key>."""

    def __init__(self, key, callback, hotkey_id=1):
        super().__init__()
        self.callback = callback
        self.hotkey_id = hotkey_id
        self.ok = bool(user32.RegisterHotKey(None, hotkey_id, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord(key)))

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                self.callback()
                return True, 0
        return False, 0

    def unregister(self):
        if self.ok:
            user32.UnregisterHotKey(None, self.hotkey_id)
            self.ok = False
