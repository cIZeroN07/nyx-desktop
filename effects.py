"""Teletransporte con rayo: Nyx se deshace, una bola de energía vuela dejando una estela
y en el destino se abre un anillo de portal donde se materializa.

Efecto inspirado en el "Zap somewhere" de capri-desktop (https://github.com/lachydotmcg/capri-desktop).
"""
import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

CYAN = QColor("#3AD6EB")
PINK = QColor("#FF2E88")
WHITE = QColor(255, 255, 255)

BURST = 0.30      # partículas al irse
FLIGHT = 0.55     # vuelo de la bola
PORTAL = 0.55     # anillo de llegada


class ZapEffect(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.timer = QTimer(self, interval=16, timeout=self._tick)
        self.on_arrive = self.on_done = None

    def play(self, start, end, on_leave, on_arrive, on_done):
        """start/end: puntos de pantalla (centro de Nyx al irse y al llegar)."""
        geo = QApplication.primaryScreen().geometry()
        self.setGeometry(geo)
        self.p0 = QPointF(start) - QPointF(geo.topLeft())
        self.p1 = QPointF(end) - QPointF(geo.topLeft())
        mid = (self.p0 + self.p1) / 2
        lift = 140 + abs(self.p1.x() - self.p0.x()) * 0.25
        self.ctrl = QPointF(mid.x(), min(self.p0.y(), self.p1.y()) - lift)
        self.sparks = [(random.uniform(0, 2 * math.pi), random.uniform(40, 140), random.choice([CYAN, PINK, WHITE]))
                       for _ in range(26)]
        self.trail = []
        self.t0 = time.monotonic()
        self.left_done = self.arrived = False
        self.on_leave, self.on_arrive, self.on_done = on_leave, on_arrive, on_done
        self.show()
        self.raise_()
        self.timer.start()

    def _pos(self, u):
        """Punto de la curva (bezier) para u de 0 a 1."""
        a, b, c = self.p0, self.ctrl, self.p1
        return a * (1 - u) ** 2 + b * 2 * u * (1 - u) + c * u * u

    def _tick(self):
        t = time.monotonic() - self.t0
        if t > BURST * 0.6 and not self.left_done:
            self.left_done = True
            self.on_leave()
        if BURST <= t <= BURST + FLIGHT:
            u = (t - BURST) / FLIGHT
            u = u * u * (3 - 2 * u)
            self.trail.append(self._pos(u))
            self.trail = self.trail[-22:]
        if t > BURST + FLIGHT and not self.arrived:
            self.arrived = True
            self.on_arrive()
        if t > BURST + FLIGHT + PORTAL:
            self.timer.stop()
            self.hide()
            self.on_done()
            return
        self.update()

    def paintEvent(self, event):
        t = time.monotonic() - self.t0
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 1) Partículas y anillo al irse
        if t < BURST + 0.25:
            k = min(1.0, t / (BURST + 0.25))
            for ang, dist, color in self.sparks:
                c = QColor(color)
                c.setAlpha(int(255 * (1 - k)))
                pos = self.p0 + QPointF(math.cos(ang), math.sin(ang)) * dist * k
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawEllipse(pos, 2.5, 2.5)
            ring = QColor(CYAN)
            ring.setAlpha(int(200 * (1 - k)))
            p.setPen(QPen(ring, 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(self.p0, 30 + 60 * k, 30 + 60 * k)

        # 2) Bola de energía con estela de rayo
        if self.trail and t <= BURST + FLIGHT + 0.12:
            path = QPainterPath(self.trail[0])
            for i, pt in enumerate(self.trail[1:], 1):
                jitter = 11 * (1 - i / len(self.trail))     # más zigzag lejos de la bola: parece un rayo
                path.lineTo(pt + QPointF(random.uniform(-jitter, jitter), random.uniform(-jitter, jitter)))
            glow = QColor(CYAN)
            glow.setAlpha(70)
            p.setPen(QPen(glow, 7))
            p.drawPath(path)
            p.setPen(QPen(WHITE, 2))
            p.drawPath(path)
            head = self.trail[-1]
            g = QRadialGradient(head, 26)
            g.setColorAt(0, WHITE)
            g.setColorAt(0.35, QColor(170, 240, 255, 230))
            g.setColorAt(0.7, QColor(255, 46, 136, 90))
            g.setColorAt(1, QColor(255, 46, 136, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(head, 26, 26)

        # 3) Portal al llegar: círculo y elipse a los pies
        if t > BURST + FLIGHT - 0.1:
            k = min(1.0, (t - (BURST + FLIGHT - 0.1)) / (PORTAL + 0.1))
            alpha = int(230 * (1 - k))
            ring = QColor(CYAN)
            ring.setAlpha(alpha)
            p.setPen(QPen(ring, 2.5))
            p.setBrush(Qt.NoBrush)
            r = 34 + 26 * k
            p.drawEllipse(self.p1, r, r)
            feet = self.p1 + QPointF(0, 70)
            p.drawEllipse(QRectF(feet.x() - 60 - 20 * k, feet.y() - 8, 120 + 40 * k, 16))
            beam = QColor(WHITE)
            beam.setAlpha(int(alpha * 0.6))
            p.setPen(QPen(beam, 2))
            p.drawLine(self.p1 + QPointF(0, -r - 120 * (1 - k)), self.p1 + QPointF(0, -r))
