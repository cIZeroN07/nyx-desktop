"""Ventana de chat estilo terminal que habla con Ollama."""
import json
import re
from datetime import datetime

import requests
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)

import config
import memory
import persona
import reminders
from spanish import FOREIGN, to_spain

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "nyx"
DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def now_text():
    n = datetime.now()
    return f"Ahora es {DAYS[n.weekday()]} {n:%d/%m/%Y}, las {n:%H:%M}."


EMOTIONS = ("normal", "pensando", "risa", "enfadada", "sorprendida")
TAG = re.compile(r"\s*\[(" + "|".join(EMOTIONS) + r")\]\s*", re.IGNORECASE)


def strip_tags(text):
    return TAG.sub(" ", text).strip()


def with_system(messages, extra=""):
    return [{"role": "system", "content": memory.system_prompt(f"{now_text()}\n{extra}".strip())}] + messages

STYLE = """
QFrame#box {
    background: rgba(12, 10, 20, 235);
    border: 1px solid #ff2d4a;
    border-radius: 8px;
}
QTextEdit {
    background: transparent;
    border: none;
    color: #ece6f0;
    selection-background-color: #ff2d4a;
}
QLineEdit {
    background: rgba(255, 45, 74, 25);
    border: 1px solid #5a2a3a;
    border-radius: 4px;
    color: #ffffff;
    padding: 6px 8px;
}
QLineEdit:focus { border: 1px solid #ff6b80; }
QPushButton#send {
    background: #ff2d4a;
    border: none;
    border-radius: 4px;
    color: #ffffff;
    font-size: 14px;
    min-width: 32px;
    min-height: 30px;
}
QPushButton#send:hover { background: #ff5068; }
QPushButton#send:disabled { background: #5a2a3a; color: #9b91a8; }
QLabel#hint { color: #7d7389; font-size: 8pt; }
"""


class OllamaWorker(QThread):
    """Pide la respuesta a Ollama en segundo plano y la va mandando a trozos."""
    token = Signal(str)
    failed = Signal(str)
    emotion = Signal(str)

    def __init__(self, messages):
        super().__init__()
        self.messages = messages

    def run(self):
        start, tag_done = "", False
        try:
            with requests.post(OLLAMA_URL, json={"model": MODEL, "messages": self.messages, "stream": True, "think": False},
                               stream=True, timeout=120) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    piece = data.get("message", {}).get("content", "")
                    if FOREIGN.search(piece):
                        break        # se ha puesto a hablar en otro idioma: cortamos aquí
                    if not tag_done:
                        # Guardar el principio hasta saber si trae la etiqueta de la cara: [risa], etc.
                        start += piece
                        if "]" not in start and len(start) < 16 and not data.get("done"):
                            continue
                        tag_done = True
                        m = TAG.match(start)
                        if m:
                            self.emotion.emit(m.group(1).lower())
                            start = start[m.end():]
                        piece = start
                    if piece:
                        self.token.emit(piece)
                    if data.get("done"):
                        break
        except requests.ConnectionError:
            self.failed.emit("No llego a Ollama. Ábrelo desde el menú Inicio y vuelve a probar.")
        except Exception as e:  # noqa: BLE001 - se lo enseñamos al usuario tal cual
            self.failed.emit(f"Error: {e}")


class FactWorker(QThread):
    """Después de cada mensaje, apunta en la memoria lo que Nyx debería recordar del usuario."""

    def __init__(self, user_text):
        super().__init__()
        self.user_text = user_text

    def run(self):
        known = "\n".join(memory.load_facts()) or "(nada)"
        prompt = memory.fact_prompt(known, self.user_text)
        try:
            r = requests.post(OLLAMA_URL, timeout=120, json={
                "model": persona.base_model(), "stream": False, "format": "json", "think": False,
                "messages": [{"role": "user", "content": prompt}], "options": {"temperature": 0}})
            facts = memory.parse_facts(r.json()["message"]["content"])
            if facts:
                memory.add_facts(facts)
        except (requests.RequestException, KeyError, ValueError):
            pass


class ReminderWorker(QThread):
    """Resume qué hay que recordar y guarda el recordatorio."""
    saved = Signal(str, str)   # texto, cuándo (bonito)

    def __init__(self, user_text, when):
        super().__init__()
        self.user_text = user_text
        self.when = when

    def run(self):
        text = None
        try:
            r = requests.post(OLLAMA_URL, timeout=120, json={
                "model": persona.base_model(), "stream": False, "format": "json", "think": False,
                "messages": [{"role": "user", "content": reminders.PROMPT.format(msg=self.user_text)}],
                "options": {"temperature": 0}})
            text = reminders.parse_text(r.json()["message"]["content"])
        except (requests.RequestException, KeyError, ValueError):
            pass
        text = text or self.user_text
        reminders.add(text, self.when)
        self.saved.emit(text, reminders.pretty(self.when))


class OneShot(QThread):
    """Pide a Nyx una frase suelta (para el bocadillo), sin guardarla en la conversación."""
    result = Signal(str)

    def __init__(self, instruction, extra=""):
        super().__init__()
        self.instruction = instruction
        self.extra = extra

    def run(self):
        try:
            r = requests.post(OLLAMA_URL, timeout=120, json={
                "model": MODEL, "stream": False, "think": False,
                "messages": with_system([{"role": "user", "content": self.instruction}], self.extra)})
            text = strip_tags(to_spain(r.json()["message"]["content"])).strip('"«» ')
            if text:
                self.result.emit(text)
        except (requests.RequestException, KeyError, ValueError):
            pass


class WarmUp(QThread):
    """Carga el modelo en la gráfica al arrancar, para que el primer mensaje no tarde."""

    def run(self):
        try:
            requests.post("http://127.0.0.1:11434/api/generate",
                          json={"model": MODEL, "prompt": "", "keep_alive": "30m"}, timeout=180)
        except requests.RequestException:
            pass


class ChatWindow(QWidget):
    talking = Signal(bool)   # True mientras Nyx está escribiendo
    replied = Signal(str)    # respuesta completa (para leerla en voz alta)
    emotion = Signal(str)    # la cara que pone: normal, pensando, risa, enfadada, sorprendida
    # Para la interfaz de terminal (talk_ui): cada paso de la conversación
    sent = Signal(str)       # lo que ha escrito el usuario
    streamed = Signal(str)   # trocito de respuesta que acaba de llegar
    finalized = Signal(str)  # respuesta completa y corregida ("" si falló)
    noted = Signal(str)      # aviso amarillo (recordatorios)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self.resize(340, 300)

        self.messages = memory.load_history()
        self.context = None          # función que devuelve qué está haciendo el usuario y el modo
        self.worker = None
        self.fact_workers = []
        self.pending_notes = []
        self.reply = ""

        box = QFrame(self, objectName="box")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)

        font = QFont("Cascadia Mono", 10)
        font.setStyleHint(QFont.Monospace)

        self.log = QTextEdit(readOnly=True)
        self.log.setFont(font)
        self.input = QLineEdit(placeholderText="Pregúntale a Nyx...")
        self.input.setFont(font)
        self.input.returnPressed.connect(self.send)
        self.send_btn = QPushButton("➤", objectName="send", toolTip="Enviar")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self.send)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.input)
        row.addWidget(self.send_btn)

        hint = QLabel("ENTER · enviar   |   ESC · cerrar", objectName="hint")
        hint.setFont(font)

        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 10, 10, 8)
        lay.addWidget(self.log)
        lay.addLayout(row)
        lay.addWidget(hint)

        # Enseñar el final de la última conversación, en gris
        for m in self.messages[-6:]:
            self._line("nyx" if m["role"] == "assistant" else "tú", strip_tags(m["content"]), old=True)
        self._line("nyx", f"Conexión establecida. ¿Qué necesitas, {config.nick()}?")

        self.warmup = WarmUp()
        self.warmup.start()

    # ---------- mostrar texto ----------
    def _line(self, who, text, old=False):
        color = "#ff6b80" if who == "nyx" else "#7fd4ff"
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if old:
            self.log.append(f'<span style="color:#6e6579">{who}&gt; {safe}</span>')
        else:
            self.log.append(f'<span style="color:{color}">{who}&gt;</span> {safe}')
        self.log.moveCursor(QTextCursor.End)

    def send_text(self, text):
        """Enviar sin escribir en la ventana (voz, interfaz de terminal)."""
        self.input.setText(text)
        self.send()

    def _append(self, piece):
        self.streamed.emit(piece)
        self.reply += piece
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(piece)
        self.log.moveCursor(QTextCursor.End)

    # ---------- enviar ----------
    def send(self):
        text = self.input.text().strip()
        if not text or self.worker is not None:
            return
        self.input.clear()
        self._line("tú", text)
        self.sent.emit(text)
        self.messages.append({"role": "user", "content": text})

        self.reply = ""
        self._line("nyx", "")
        self.reply_start = self.log.textCursor().position()
        self.send_btn.setEnabled(False)
        self.talking.emit(True)

        # ¿Es un recordatorio? La fecha se calcula aquí; a Nyx solo le contamos el resultado
        extra = ""
        if reminders.TRIGGER.search(text):
            when = reminders.when_from(text)
            if when:
                extra = (f"{config.name()} te ha pedido un recordatorio y ya está guardado para {reminders.pretty(when)}. "
                         "Confírmaselo en una frase corta.")
                rw = ReminderWorker(text, when)
                rw.saved.connect(self._reminder_saved)
                rw.finished.connect(lambda: self.fact_workers.remove(rw))
                self.fact_workers.append(rw)
                rw.start()
            else:
                extra = f"{config.name()} quiere que le recuerdes algo pero no ha dicho cuándo: pregúntale el día o la hora."

        if self.context:
            extra = "\n".join(t for t in (self.context(), extra) if t)
        self.last_emotion = "normal"
        self.worker = OllamaWorker(with_system(self.messages, extra))
        self.worker.emotion.connect(self._on_emotion)

        # En paralelo, apuntar lo que haya que recordar de este mensaje
        fw = FactWorker(text)
        fw.finished.connect(lambda: self.fact_workers.remove(fw))
        self.fact_workers.append(fw)
        fw.start()
        self.worker.token.connect(self._append)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._done)
        self.worker.start()

    def _on_emotion(self, name):
        self.last_emotion = name
        self.emotion.emit(name)

    def note(self, text):
        """Línea amarilla de aviso. Si Nyx está escribiendo, se enseña al terminar."""
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.noted.emit(text)
        self.pending_notes.append(f'<span style="color:#ffd166">⏰ {safe}</span>')
        if self.worker is None:
            self._flush_notes()

    def _reminder_saved(self, text, when):
        self.note(f"Recordatorio: {text} · {when}")

    def _flush_notes(self):
        for note in self.pending_notes:
            self.log.append(note)
        self.pending_notes = []
        self.log.moveCursor(QTextCursor.End)

    def _failed(self, msg):
        self._append(msg)
        self.messages.pop()          # no guardar la pregunta que no tuvo respuesta
        self.reply = ""

    def _done(self):
        if self.reply:
            # Al terminar, cambiar lo que se le haya escapado en español latino
            fixed = strip_tags(to_spain(self.reply))
            if fixed != self.reply:
                cursor = self.log.textCursor()
                cursor.setPosition(self.reply_start)
                cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
                cursor.insertText(fixed)
                self.reply = fixed
            # En el historial se guarda con la etiqueta, para que siga acordándose de ponerla
            self.messages.append({"role": "assistant", "content": f"[{self.last_emotion}] {self.reply}"})
            self.replied.emit(self.reply)
        self.messages = self.messages[-memory.MAX_HISTORY:]   # solo lo último, para que vaya rápido
        memory.save_history(self.messages)
        self.worker = None
        self.finalized.emit(self.reply)
        self._flush_notes()
        self.send_btn.setEnabled(True)
        self.talking.emit(False)

    # ---------- abrir / cerrar ----------
    def show_near(self, nyx_rect):
        screen = self.screen().availableGeometry() if self.screen() else nyx_rect
        x = nyx_rect.left() - self.width() - 8
        if x < screen.left():
            x = nyx_rect.right() + 8
        y = max(screen.top(), nyx_rect.top() + 20)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def forget(self):
        memory.clear()
        self.messages = []
        self.log.clear()
        self._line("nyx", f"Memoria borrada. Empezamos de cero, {config.nick()}.")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
