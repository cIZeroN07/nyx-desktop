"""Interfaz estilo terminal: pastilla (lápiz / ondas / micro), bocadillo con efecto máquina de escribir
y caja para escribir.

Basada en el diseño de la interfaz de capri-desktop (https://github.com/lachydotmcg/capri-desktop),
reescrita en Python. Licencia PolyForm Noncommercial 1.0.0 (https://polyformproject.org/licenses/noncommercial/1.0.0).
Required Notice: Copyright 2026 Lachy (https://github.com/lachydotmcg)
"""
import random
import textwrap
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

import config

BG = QColor(9, 11, 15, 238)
CYAN = QColor("#3AD6EB")
RED = QColor("#E82440")
BLUE = QColor("#38B0FF")
INK = QColor("#E8ECF0")
DIM = QColor("#7A808A")
YELLOW = QColor("#F4D646")
PILL_FILL = QColor(20, 21, 25, 245)
EDGE = QColor("#464952")
COLS = 34            # columnas de texto del bocadillo
MAX_LINES = 12
TAIL = 12

_family = None


def mono(size=11.0, bold=False, italic=False):
    global _family
    if _family is None:
        fid = QFontDatabase.addApplicationFont(str(config.APP_DIR / "assets" / "fonts" / "ShareTechMono-Regular.ttf"))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        _family = fams[0] if fams else "Cascadia Mono"
    f = QFont(_family)
    f.setPointSizeF(size)
    f.setBold(bold)
    f.setItalic(italic)
    f.setStyleHint(QFont.Monospace)
    return f


def neon_menu(parent=None, title=None):
    """Menú de clic derecho al estilo de capri-desktop: oscuro, redondeado y con la selección en rosa."""
    from PySide6.QtWidgets import QMenu
    menu = QMenu(title, parent) if title else QMenu(parent)
    menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WA_TranslucentBackground)
    family = mono().family()
    menu.setStyleSheet(f"""
        QMenu {{ background: rgba(9, 11, 15, 246); border: 1px solid #2B3038; border-radius: 9px;
                 padding: 6px 0; color: #E8ECF0; font-family: "{family}"; font-size: 10.5pt; }}
        QMenu::item {{ padding: 6px 26px 6px 28px; margin: 1px 6px; border-radius: 5px; }}
        QMenu::item:selected {{ background: #FF2E88; color: #FFFFFF; }}
        QMenu::item:disabled {{ color: #5D636C; }}
        QMenu::separator {{ height: 1px; background: #2B3038; margin: 5px 12px; }}
        QMenu::indicator {{ width: 8px; height: 8px; left: 12px; }}
        QMenu::indicator:checked {{ background: #3AD6EB; border-radius: 4px; }}
        QMenu::indicator:unchecked {{ background: transparent; }}
        QMenu::right-arrow {{ width: 8px; height: 8px; right: 10px; }}
    """)
    return menu


class Overlay(QWidget):
    """Ventana flotante transparente con efecto glitch al abrir y cerrar."""

    def __init__(self, focus=False):
        super().__init__()
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        if not focus:
            flags |= Qt.WindowDoesNotAcceptFocus
            self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.glitch_end = 0.0
        self.hide_after_glitch = False
        self.glitch_timer = QTimer(self, interval=30, timeout=self._glitch_tick)

    def glitch(self, ms, then_hide=False):
        self.glitch_end = time.monotonic() + ms / 1000
        self.hide_after_glitch = then_hide
        self.glitch_timer.start()
        self.update()

    def _glitch_tick(self):
        if time.monotonic() >= self.glitch_end:
            self.glitch_timer.stop()
            if self.hide_after_glitch:
                self.hide_after_glitch = False
                QWidget.hide(self)
        self.update()

    def draw(self, p):
        raise NotImplementedError

    def paintEvent(self, event):
        p = QPainter(self)
        if time.monotonic() >= self.glitch_end:
            p.setRenderHint(QPainter.Antialiasing)
            self.draw(p)
            return
        # Pintar en una imagen y dibujarla a franjas desplazadas
        dpr = self.devicePixelRatioF()
        buf = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        buf.setDevicePixelRatio(dpr)
        buf.fill(Qt.transparent)
        bp = QPainter(buf)
        bp.setRenderHint(QPainter.Antialiasing)
        self.draw(bp)
        bp.end()
        y = 0
        while y < self.height():
            step = random.randint(3, 12)
            off = random.randint(-9, 9) if random.random() < 0.4 else 0
            p.drawPixmap(QRectF(off, y, self.width(), step), buf, QRectF(0, y * dpr, self.width() * dpr, step * dpr))
            y += step
        for _ in range(random.randint(1, 3)):
            c = QColor(CYAN if random.random() < 0.5 else RED)
            c.setAlpha(70)
            p.fillRect(QRectF(random.randint(0, self.width() // 2), random.randint(0, self.height()),
                              random.randint(20, self.width()), random.randint(2, 5)), c)


# ---------------------------------------------------------------- bocadillo
class SpeechBox(Overlay):
    """Bocadillo de terminal: «> you: ...» y «NYX: ...» escribiéndose letra a letra."""

    def __init__(self):
        super().__init__()
        self.font_text = mono(11)
        self.font_you = mono(11, italic=True)
        self.font_name = mono(11, bold=True)
        fm = QFontMetricsF(self.font_text)
        self.cw, self.lh = fm.horizontalAdvance("M"), fm.height() * 1.15
        self.pad = 14
        self.you = None
        self.target = ""
        self.shown = 0
        self.notes = []
        self.thinking = False
        self.done = True
        self.cursor_on = True
        self.anchor = None
        self.tail_down = True
        self.type_timer = QTimer(self, interval=22, timeout=self._type)
        self.blink_timer = QTimer(self, interval=250, timeout=self._blink)
        self.close_timer = QTimer(self, singleShot=True, timeout=self.close_box)

    # --- API ---
    def busy(self):
        """¿Está a mitad de una conversación?"""
        return self.isVisible() and (self.thinking or not self.done)

    def show_exchange(self, you_text, anchor):
        self.you, self.target, self.shown, self.notes = you_text, "", 0, []
        self.thinking, self.done = True, False
        self.close_timer.stop()
        self._open(anchor)

    def add_reply(self, piece):
        self.thinking = False
        self.target += piece
        self.type_timer.start()

    def set_reply(self, text):
        """Texto final (ya corregido). Si cambia lo ya escrito, se ajusta."""
        self.target = text
        self.shown = min(self.shown, len(text))
        self.type_timer.start()

    def finish(self):
        self.thinking = False
        self.done = True
        self._schedule_close()

    def note(self, text):
        self.notes.append(text)
        self._relayout()

    def say(self, text, anchor, ms=None):
        """Lo que antes era el bocadillo simple: Nyx dice algo sola."""
        if self.busy():
            return
        self.you, self.target, self.shown, self.notes = None, text, 0, []
        self.thinking, self.done = False, True
        self._open(anchor)
        self.type_timer.start()
        self._schedule_close(ms)

    def follow(self, anchor):
        if self.isVisible():
            self.anchor = anchor
            self._relayout()

    def close_box(self):
        if self.isVisible():
            self.glitch(250, then_hide=True)

    def hide(self):
        self.close_timer.stop()
        super().hide()

    # --- interno ---
    def _open(self, anchor):
        self.anchor = anchor
        self.blink_timer.start()
        self._relayout()
        if not self.isVisible():
            self.show()
            self.glitch(200)
        self.raise_()

    def _schedule_close(self, ms=None):
        self.close_timer.start(ms or (6000 + 55 * len(self.target)))

    def _type(self):
        if self.shown < len(self.target):
            self.shown = min(len(self.target), self.shown + 2)
            self._relayout()
        else:
            self.type_timer.stop()

    def _blink(self):
        self.blink_timer.setInterval(200 if self.thinking else 250)
        self.cursor_on = not self.cursor_on if (self.thinking or self.done) else True
        self.update()

    def _lines(self):
        """[(texto, tipo)] ya cortadas a COLS columnas."""
        out = []
        if self.you is not None:
            you = self.you if len(self.you) <= COLS - 7 else self.you[:COLS - 10] + "..."
            out.append(("> you: " + you, "you"))
        body = textwrap.wrap("NYX: " + self.target[:self.shown], COLS) or ["NYX: "]
        for i, line in enumerate(body):
            out.append((line, "first" if i == 0 else "reply"))
        for n in self.notes:
            for line in textwrap.wrap("⏰ " + n, COLS):
                out.append((line, "note"))
        return out[-MAX_LINES:]

    def _relayout(self):
        lines = self._lines()
        w = int(self.cw * COLS + self.pad * 2 + 8)
        h = int(len(lines) * self.lh + self.pad * 2 + TAIL)
        self.resize(w, h)
        if self.anchor is not None:
            screen = QApplication.primaryScreen().availableGeometry()
            x = self.anchor.center().x() - w // 2
            y = self.anchor.top() - h + 14
            self.tail_down = y >= screen.top()
            if not self.tail_down:
                y = self.anchor.bottom() - 10
            x = max(screen.left() + 12, min(x, screen.right() - w - 12))
            self.move(int(x), int(y))
        self.update()

    def draw(self, p):
        w, h = self.width(), self.height()
        top = 0 if self.tail_down else TAIL
        body = QRectF(4, top + 4, w - 8, h - TAIL - 8)
        path = QPainterPath()
        path.addRoundedRect(body, 10, 10)
        tx = min(max(self.anchor.center().x() - self.x(), 30), w - 30) if self.anchor else w / 2
        tail = QPainterPath()
        if self.tail_down:
            tail.moveTo(tx - 9, body.bottom() - 1)
            tail.lineTo(tx, body.bottom() + TAIL - 2)
            tail.lineTo(tx + 9, body.bottom() - 1)
        else:
            tail.moveTo(tx - 9, body.top() + 1)
            tail.lineTo(tx, body.top() - TAIL + 2)
            tail.lineTo(tx + 9, body.top() + 1)
        tail.closeSubpath()
        path = path.united(tail)

        glow = QColor(CYAN)
        glow.setAlpha(46)
        p.setPen(QPen(glow, 7))
        p.drawPath(path)
        p.fillPath(path, BG)
        p.setPen(QPen(CYAN, 2))
        p.drawPath(path)

        # Líneas de escaneo y barra roja
        p.save()
        p.setClipPath(path)
        scan = QColor(255, 255, 255, 8)
        for y in range(int(body.top()), int(body.bottom()), 3):
            p.fillRect(QRectF(body.left(), y, body.width(), 1), scan)
        p.restore()
        p.fillRect(QRectF(body.left() + 6, body.top() + 10, 3, body.height() - 20), RED)

        x0 = body.left() + self.pad + 4
        y = body.top() + self.pad + QFontMetricsF(self.font_text).ascent()
        last_end = QPointF(x0, y)
        for text, kind in self._lines():
            if kind == "you":
                p.setFont(self.font_you)
                p.setPen(DIM)
                p.drawText(QPointF(x0, y), text)
            elif kind == "first":
                p.setFont(self.font_name)
                p.setPen(RED)
                p.drawText(QPointF(x0, y), "NYX:")
                p.setFont(self.font_text)
                p.setPen(BLUE)
                p.drawText(QPointF(x0 + self.cw * 5, y), text[5:])
                last_end = QPointF(x0 + self.cw * len(text), y)
            elif kind == "note":
                p.setFont(self.font_text)
                p.setPen(YELLOW)
                p.drawText(QPointF(x0, y), text)
            else:
                p.setFont(self.font_text)
                p.setPen(BLUE)
                p.drawText(QPointF(x0, y), text)
                last_end = QPointF(x0 + self.cw * len(text), y)
            y += self.lh
        # Cursor de bloque
        if self.cursor_on:
            fm = QFontMetricsF(self.font_text)
            p.fillRect(QRectF(last_end.x() + 2, last_end.y() - fm.ascent() + 2, self.cw * 0.8, fm.ascent()), BLUE)

    def mousePressEvent(self, event):
        self.close_box()


# ---------------------------------------------------------------- caja para escribir
class InputBox(Overlay):
    submitted = Signal(str)

    def __init__(self):
        super().__init__(focus=True)
        self.edit = QLineEdit(self)
        self.edit.setFont(mono(11))
        self.edit.setMaxLength(240)
        self.edit.setStyleSheet("QLineEdit { background: transparent; border: none; color: #E8ECF0; "
                                "selection-background-color: #E82440; }")
        self.edit.returnPressed.connect(self._send)
        fm = QFontMetricsF(mono(11))
        self.resize(int(fm.horizontalAdvance("M") * COLS + 36), 44)
        self.label_w = fm.horizontalAdvance("> you: ")
        self.edit.setGeometry(int(22 + self.label_w), 10, int(self.width() - 34 - self.label_w), 24)
        QApplication.instance().focusChanged.connect(self._focus_changed)

    def open_at(self, x, y):
        self.move(int(x), int(y))
        if not self.isVisible():
            self.show()
            self.glitch(200)
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def _send(self):
        text = self.edit.text().strip()
        if text:
            self.edit.clear()
            self.submitted.emit(text)
        self.glitch(250, then_hide=True)

    def _focus_changed(self, old, new):
        if self.isVisible() and old is self.edit and new is None:
            QTimer.singleShot(150, lambda: not self.isActiveWindow() and self.glitch(250, then_hide=True))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.glitch(250, then_hide=True)
        else:
            super().keyPressEvent(event)

    def draw(self, p):
        r = QRectF(3, 3, self.width() - 6, self.height() - 6)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, BG)
        p.setPen(QPen(CYAN, 2))
        p.drawPath(path)
        p.fillRect(QRectF(r.left() + 10, r.top() + 9, 3, r.height() - 18), RED)
        p.setFont(mono(11, italic=True))
        p.setPen(DIM)
        p.drawText(QPointF(22, self.height() / 2 + 5), "> you:")


# ---------------------------------------------------------------- pastilla
class TalkPill(Overlay):
    """Pastilla con lápiz (escribir) y ondas (hablar). En modo voz aparece el botón del micro."""
    type_clicked = Signal()
    voice_clicked = Signal()
    mic_clicked = Signal()

    W, H, GAP = 100, 40, 8

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.voice_mode = False
        self.muted = False
        self.level = 0.0
        self.hover = None
        self._resize()

    def set_voice_mode(self, on):
        self.voice_mode = on
        self._resize()

    def set_muted(self, on):
        self.muted = on
        self.update()

    def set_level(self, level):
        self.level = max(0.0, min(1.0, level))
        if self.voice_mode:
            self.update()

    def _resize(self):
        self.resize(self.W + (self.GAP + self.H if self.voice_mode else 0), self.H)
        self.update()

    def _zone(self, x):
        if x < self.W / 2:
            return "type"
        if x < self.W:
            return "voice"
        if self.voice_mode and x > self.W + self.GAP:
            return "mic"
        return None

    def mouseMoveEvent(self, event):
        z = self._zone(event.position().x())
        if z != self.hover:
            self.hover = z
            self.update()

    def leaveEvent(self, event):
        self.hover = None
        self.update()

    def mouseReleaseEvent(self, event):
        z = self._zone(event.position().x())
        {"type": self.type_clicked, "voice": self.voice_clicked, "mic": self.mic_clicked}.get(z, None) and \
            {"type": self.type_clicked, "voice": self.voice_clicked, "mic": self.mic_clicked}[z].emit()

    def draw(self, p):
        r = QRectF(3, 3, self.W - 6, self.H - 6)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, PILL_FILL)
        p.setPen(QPen(EDGE, 1.5))
        p.drawPath(path)
        p.drawLine(QPointF(self.W / 2, 10), QPointF(self.W / 2, self.H - 10))

        for zone, cx in (("type", self.W * 0.25), ("voice", self.W * 0.75)):
            if self.hover == zone:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 30))
                p.drawEllipse(QPointF(cx, self.H / 2), 15, 15)

        # Lápiz
        p.save()
        p.translate(self.W * 0.25, self.H / 2)
        p.rotate(-45)
        color = CYAN if self.hover == "type" else INK
        p.setPen(QPen(color, 1.6))
        p.setBrush(QColor(9, 11, 15))
        p.drawRoundedRect(QRectF(-9, -3.5, 14, 7), 1.5, 1.5)
        tip = QPainterPath()
        tip.moveTo(5, -3.5)
        tip.lineTo(10, 0)
        tip.lineTo(5, 3.5)
        tip.closeSubpath()
        p.drawPath(tip)
        p.drawLine(QPointF(-5, -3.5), QPointF(-5, 3.5))
        p.restore()

        # Ondas
        active = self.voice_mode
        color = CYAN if (active or self.hover == "voice") else INK
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        heights = [5, 10, 14, 9, 4]
        cx = self.W * 0.75 - 7.2
        for i, base in enumerate(heights):
            hgt = base * 1.25
            if active:
                hgt = max(4.0, base * 1.25 * (0.35 + self.level * 1.6 * random.uniform(0.7, 1.2)))
            p.drawRoundedRect(QRectF(cx + i * 3.6 - 1.2, self.H / 2 - hgt / 2, 2.4, hgt), 1.2, 1.2)

        # Micro (solo en modo voz)
        if self.voice_mode:
            mx = self.W + self.GAP + self.H / 2
            circle = QRectF(self.W + self.GAP + 3, 3, self.H - 6, self.H - 6)
            p.setBrush(PILL_FILL)
            p.setPen(QPen(EDGE, 1.5))
            p.drawEllipse(circle)
            color = CYAN if self.hover == "mic" else INK
            p.setPen(QPen(color, 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(mx - 3.5, self.H / 2 - 9, 7, 12), 3.5, 3.5)
            p.drawArc(QRectF(mx - 7, self.H / 2 - 6, 14, 12), 200 * 16, 140 * 16)
            p.drawLine(QPointF(mx, self.H / 2 + 6), QPointF(mx, self.H / 2 + 9))
            if self.muted:
                p.setPen(QPen(QColor(9, 11, 15), 4))
                p.drawLine(QPointF(mx - 9, self.H / 2 - 9), QPointF(mx + 9, self.H / 2 + 9))
                p.setPen(QPen(RED, 2))
                p.drawLine(QPointF(mx - 9, self.H / 2 - 9), QPointF(mx + 9, self.H / 2 + 9))

    def follow(self, anchor):
        """Al lado de Nyx, a la altura de las rodillas; si no cabe a la izquierda, a la derecha."""
        screen = QApplication.primaryScreen().availableGeometry()
        x = anchor.left() - self.width() - 6
        if x < screen.left():
            x = anchor.right() + 6
        y = anchor.bottom() - self.H - 30
        self.move(int(x), int(min(y, screen.bottom() - self.H)))
