"""Bocadillo de cómic que aparece encima de la cabeza de Nyx."""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

TAIL = 10        # altura del piquito que apunta a Nyx
MAX_WIDTH = 230


class Bubble(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        font = QFont("Cascadia Mono", 9)
        font.setStyleHint(QFont.Monospace)
        self.label = QLabel(wordWrap=True)
        self.label.setFont(font)
        self.label.setStyleSheet("color: #ece6f0;")
        self.label.setMaximumWidth(MAX_WIDTH - 24)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9 + TAIL)
        lay.addWidget(self.label)

        self.timer = QTimer(self, singleShot=True, timeout=self.hide)

    def say(self, text, anchor, ms=None):
        """Muestra `text` encima del rectángulo `anchor` (la ventana de Nyx)."""
        self.label.setText(text)
        self.adjustSize()
        x = anchor.center().x() - self.width() // 2
        y = anchor.top() - self.height() + 6
        self.move(x, max(0, y))
        self.show()
        self.raise_()
        # Que dure según lo largo que sea el texto
        self.timer.start(ms or min(12000, 3000 + 60 * len(text)))

    def mousePressEvent(self, event):
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        body = QRectF(1, 1, self.width() - 2, self.height() - TAIL - 2)
        path = QPainterPath()
        path.addRoundedRect(body, 8, 8)
        cx = body.center().x()
        tail = QPainterPath()
        tail.moveTo(QPointF(cx - 8, body.bottom() - 1))
        tail.lineTo(QPointF(cx, body.bottom() + TAIL))
        tail.lineTo(QPointF(cx + 8, body.bottom() - 1))
        tail.closeSubpath()
        path = path.united(tail)
        p.fillPath(path, QColor(12, 10, 20, 235))
        p.setPen(QPen(QColor("#ff2d4a"), 1.2))
        p.drawPath(path)
