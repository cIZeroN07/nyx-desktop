"""Modo travesura: Nyx se "glitchea" y suelta interferencias por la pantalla."""
import io
import random

import numpy as np
from PIL import Image
from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

SHIFT = 8   # separación de colores (aberración cromática), en píxeles


def _to_pixmap(arr):
    buf = io.BytesIO()
    Image.fromarray(arr, "RGBA").save(buf, "PNG")
    pix = QPixmap()
    pix.loadFromData(buf.getvalue(), "PNG")
    return pix


def make_frames(pixmap_path, size, count=4):
    """Versiones "rotas" del sprite: colores separados, franjas desplazadas y líneas de escaneo."""
    img = Image.open(pixmap_path).convert("RGBA").resize(size, Image.LANCZOS)
    src = np.array(img)
    h, w = src.shape[:2]
    frames = []
    for _ in range(count):
        out = np.zeros((h, w + 2 * SHIFT, 4), np.uint8)
        base = np.zeros_like(out)
        base[:, SHIFT:SHIFT + w] = src
        red = np.roll(base, -random.randint(3, SHIFT), axis=1)
        cyan = np.roll(base, random.randint(3, SHIFT), axis=1)
        out[..., 0] = red[..., 0]
        out[..., 1] = cyan[..., 1]
        out[..., 2] = cyan[..., 2]
        out[..., 3] = np.maximum(base[..., 3], np.maximum(red[..., 3], cyan[..., 3]) // 2)
        # Franjas horizontales desplazadas
        for _ in range(random.randint(4, 8)):
            y0 = random.randint(0, h - 10)
            y1 = min(h, y0 + random.randint(4, 24))
            out[y0:y1] = np.roll(out[y0:y1], random.randint(-18, 18), axis=1)
        # Líneas de escaneo
        out[::3, :, :3] = (out[::3, :, :3] * 0.7).astype(np.uint8)
        frames.append(_to_pixmap(out))
    return frames


class ScreenGlitch(QWidget):
    """Interferencias a pantalla completa durante un instante. No bloquea el ratón."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.bars = []
        self.frames_left = 0
        self.timer = QTimer(self, interval=60, timeout=self._next)

    def play(self, frames=9):
        self.setGeometry(QApplication.primaryScreen().geometry())
        self.frames_left = frames
        self._next()
        self.show()
        self.timer.start()

    def _next(self):
        if self.frames_left <= 0:
            self.timer.stop()
            self.hide()
            return
        self.frames_left -= 1
        w, h = self.width(), self.height()
        self.bars = []
        for _ in range(random.randint(3, 9)):
            y = random.randint(0, h)
            color = random.choice([QColor(255, 45, 74, 90), QColor(0, 230, 255, 80), QColor(255, 255, 255, 40)])
            self.bars.append((QRect(random.randint(-200, w // 2), y, random.randint(w // 4, w), random.randint(2, 18)),
                              color))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        for rect, color in self.bars:
            p.fillRect(rect, color)
