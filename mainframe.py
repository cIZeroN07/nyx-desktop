"""MAINFRAME: ventana de ajustes de Nyx (cerebro, voz, aspecto y comportamiento).

Diseño inspirado en el "Mainframe" de capri-desktop (https://github.com/lachydotmcg/capri-desktop).
"""
from PySide6.QtCore import QPoint, QThread, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

import config
import persona
import talk_ui
import voice as voice_mod

VERSION = "v1.1"
SIZES = {"small": 220, "medium": 300, "large": 390}


def _style(family):
    return f"""
    QWidget#root {{ background: #090B0F; border: 1px solid #2B3038; border-radius: 10px; }}
    QWidget {{ color: #E8ECF0; font-family: "{family}"; font-size: 10pt; }}
    QLabel#title {{ font-size: 15pt; font-weight: 700; letter-spacing: 2px; }}
    QLabel#version {{ color: #7A808A; }}
    QLabel#section {{ color: #F4D646; font-weight: 700; letter-spacing: 1px; }}
    QLabel#big {{ font-size: 12pt; font-weight: 700; }}
    QLabel#dim {{ color: #7A808A; }}
    QLabel#warn {{ color: #E82440; }}
    QFrame#block {{ border: none; border-left: 3px solid #E82440; }}
    QFrame#line {{ background: #2B3038; max-height: 1px; }}
    QPushButton {{ background: #12151B; border: 1px solid #3A3F48; border-radius: 6px; padding: 6px 12px; }}
    QPushButton:hover {{ border-color: #3AD6EB; color: #3AD6EB; }}
    QPushButton[active="true"] {{ border: 1px solid #3AD6EB; color: #3AD6EB; background: #0F2A30; }}
    QPushButton#danger {{ color: #E82440; }}
    QPushButton#danger:hover {{ border-color: #E82440; }}
    QPushButton#close {{ background: transparent; border: none; color: #7A808A; font-size: 13pt; padding: 0 6px; }}
    QPushButton#close:hover {{ color: #E82440; }}
    QLineEdit, QComboBox {{ background: #12151B; border: 1px solid #3A3F48; border-radius: 6px; padding: 6px 8px; }}
    QLineEdit:focus, QComboBox:focus {{ border-color: #3AD6EB; }}
    QComboBox QAbstractItemView {{ background: #12151B; border: 1px solid #3A3F48; selection-background-color: #FF2E88; }}
    QCheckBox::indicator {{ width: 12px; height: 12px; border: 1px solid #3A3F48; background: #12151B; }}
    QCheckBox::indicator:checked {{ background: #3AD6EB; border-color: #3AD6EB; }}
    """


class Job(QThread):
    """Ejecuta algo lento (internet, Ollama, micro) sin congelar la ventana."""
    done = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as e:  # noqa: BLE001
            self.done.emit(e)


class Mainframe(QWidget):
    def __init__(self, nyx):
        super().__init__()
        self.nyx = nyx
        self.voice = nyx.voice
        self.jobs = []
        self.drag = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(_style(talk_ui.mono().family()))
        self.setFixedWidth(400)

        root = QWidget(objectName="root")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(12)

        # Cabecera
        head = QHBoxLayout()
        head.addWidget(QLabel("MAINFRAME", objectName="title"))
        head.addStretch()
        head.addWidget(QLabel(VERSION, objectName="version"))
        close = QPushButton("✕", objectName="close")
        close.clicked.connect(self.hide)
        head.addWidget(close)
        lay.addLayout(head)

        lay.addWidget(self._brain())
        lay.addWidget(self._voice())
        lay.addWidget(self._body())

        bottom = QHBoxLayout()
        profile = QPushButton("Cambiar mi perfil")
        profile.clicked.connect(nyx.edit_profile)
        quit_ = QPushButton("Apagar a Nyx", objectName="danger")
        quit_.clicked.connect(lambda: __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication.quit())
        bottom.addWidget(profile)
        bottom.addStretch()
        bottom.addWidget(quit_)
        lay.addLayout(bottom)

    # ---------- utilidades ----------
    def _section(self, title):
        frame = QFrame(objectName="block")
        v = QVBoxLayout(frame)
        v.setContentsMargins(10, 2, 0, 2)
        v.setSpacing(8)
        v.addWidget(QLabel(f"{title} >", objectName="section"))
        return frame, v

    def _run(self, fn, done):
        job = Job(fn)
        job.done.connect(done)
        job.finished.connect(lambda: self.jobs.remove(job))
        self.jobs.append(job)
        job.start()

    @staticmethod
    def _row(*widgets, stretch_first=True):
        h = QHBoxLayout()
        h.setSpacing(8)
        for i, w in enumerate(widgets):
            h.addWidget(w, 1 if (i == 0 and stretch_first) else 0)
        return h

    # ---------- CEREBRO ----------
    def _brain(self):
        frame, v = self._section("CEREBRO")
        self.brain_name = QLabel("", objectName="big")
        self.brain_status = QLabel("", objectName="dim")
        self.brain_combo = QComboBox()
        refresh = QPushButton("Actualizar")
        refresh.clicked.connect(self.refresh_brain)
        self.brain_combo.activated.connect(self._choose_brain)
        v.addWidget(self.brain_name)
        v.addWidget(self.brain_status)
        v.addLayout(self._row(self.brain_combo, refresh))
        self.refresh_brain()
        return frame

    def refresh_brain(self):
        self.brain_name.setText(f"Ollama · {persona.base_model()}")
        self.brain_status.setText("Comprobando...")

        def check():
            return persona.ollama_running(), sorted(m for m in persona.installed_models() if not m.startswith("nyx"))

        def done(result):
            if isinstance(result, Exception):
                result = (False, [])
            running, models = result
            self.brain_status.setText("Funcionando en este PC" if running else "Ollama está cerrado")
            self.brain_combo.clear()
            for m in models:
                self.brain_combo.addItem(m)
            current = persona.base_model()
            idx = self.brain_combo.findText(current)
            if idx < 0 and self.brain_combo.findText(current + ":latest") >= 0:
                idx = self.brain_combo.findText(current + ":latest")
            self.brain_combo.setCurrentIndex(max(idx, 0))
        self._run(check, done)

    def _choose_brain(self, _i):
        model = self.brain_combo.currentText()
        if not model or model == persona.base_model():
            return
        self.voice.set("base_model", model)
        self.brain_status.setText(f"Pasando la personalidad a {model}...")

        def done(result):
            if isinstance(result, Exception):
                self.brain_status.setText(f"No he podido: {result}")
            else:
                self.brain_name.setText(f"Ollama · {model}")
                self.brain_status.setText("Listo. Ya piensa con el cerebro nuevo.")
        self._run(persona.create_model, done)

    # ---------- VOZ ----------
    def _voice(self):
        frame, v = self._section("VOZ")
        s = self.voice.settings

        self.voice_on = QCheckBox("Hablar en voz alta")
        self.voice_on.setChecked(self.voice.on)
        self.voice_on.toggled.connect(self.nyx._toggle_voice)
        self.only_hp = QCheckBox("Solo con cascos")
        self.only_hp.setChecked(s["only_headphones"])
        self.only_hp.toggled.connect(lambda val: self.voice.set("only_headphones", val))
        v.addLayout(self._row(self.voice_on, self.only_hp, stretch_first=False))

        # Voz de Microsoft (gratis)
        self.ms_voice = QComboBox()
        self.ms_voice.addItems(list(voice_mod.VOICES))
        self.ms_voice.setCurrentText(s.get("voice", "Elvira"))
        self.ms_voice.activated.connect(lambda _i: self.voice.set("voice", self.ms_voice.currentText()))
        test_ms = QPushButton("Probar")
        test_ms.clicked.connect(lambda: self.nyx._choose_voice(self.ms_voice.currentText()))
        v.addWidget(QLabel("Voz gratis (Microsoft)", objectName="dim"))
        v.addLayout(self._row(self.ms_voice, test_ms))

        # ElevenLabs
        v.addWidget(QLabel("ElevenLabs (más natural, para el chat)", objectName="dim"))
        get_key = QPushButton("Conseguir clave")
        get_key.clicked.connect(lambda: __import__("webbrowser").open("https://elevenlabs.io/app/settings/api-keys"))
        self.key = QLineEdit(s.get("eleven_key", ""), placeholderText="Pega aquí tu clave de ElevenLabs")
        self.key.setEchoMode(QLineEdit.Password)
        connect = QPushButton("Conectar")
        connect.clicked.connect(self._connect_eleven)
        v.addLayout(self._row(self.key, connect))
        self.voice_id = QLineEdit(s.get("eleven_voice", ""), placeholderText="Voice ID (de la Voice Library)")
        self.model = QComboBox()
        self.model.addItem("Rápida", "flash")
        self.model.addItem("Natural", "natural")
        self.model.setCurrentIndex(0 if s.get("eleven_model", "flash") == "flash" else 1)
        self.model.activated.connect(lambda _i: self.voice.set("eleven_model", self.model.currentData()))
        v.addLayout(self._row(self.voice_id, self.model))
        use_id = QPushButton("Usar esta voz")
        use_id.clicked.connect(self._use_voice_id)
        v.addLayout(self._row(use_id, get_key, stretch_first=False))
        self.eleven_status = QLabel("", objectName="dim", wordWrap=True)
        v.addWidget(self.eleven_status)

        # Micrófono
        self.mic = QComboBox()
        self.mic.addItem("Micro: el de Windows", None)
        for name, idx in voice_mod.list_mics():
            self.mic.addItem(f"Micro: {name}", idx)
            if s.get("mic") == idx:
                self.mic.setCurrentIndex(self.mic.count() - 1)
        self.mic.activated.connect(lambda _i: self.voice.set("mic", self.mic.currentData()))
        test_mic = QPushButton("Probar")
        test_mic.clicked.connect(self._test_mic)
        v.addLayout(self._row(self.mic, test_mic))
        self.mic_status = QLabel("Habla mientras pruebas. Ctrl + Alt + Espacio: hablarle · Ctrl + Alt + M: callarla",
                                 objectName="dim", wordWrap=True)
        v.addWidget(self.mic_status)
        self._eleven_text()
        return frame

    def _eleven_text(self):
        s = self.voice.settings
        if not s.get("eleven_key"):
            self.eleven_status.setText("Sin clave: usa la voz gratis de Microsoft.")
        elif not s.get("eleven_voice"):
            self.eleven_status.setText("Clave puesta. Falta elegir una voz (Voice ID).")
        else:
            self.eleven_status.setText("ElevenLabs activo en las respuestas del chat.")

    def _connect_eleven(self):
        key = self.key.text().strip()
        if not key:
            return
        self.eleven_status.setText("Comprobando la clave...")

        def done(result):
            if isinstance(result, Exception):
                self.eleven_status.setText("Esa clave no funciona. Revisa que esté entera.")
                return
            self.voice.set("eleven_key", key)
            self.voice.set("eleven_voices", result)
            self.voice.set("eleven_on", True)
            if not self.voice.settings.get("eleven_voice") and result:
                self.voice.set("eleven_voice", result[0][1])
                self.voice_id.setText(result[0][1])
            self._eleven_text()
        self._run(lambda: voice_mod.eleven_voices(key), done)

    def _use_voice_id(self):
        vid = self.voice_id.text().strip()
        if not vid or not self.voice.settings.get("eleven_key"):
            self.eleven_status.setText("Primero conecta tu clave y pega un Voice ID.")
            return
        voices = [v for v in self.voice.settings.get("eleven_voices", []) if v[1] != vid]
        voices.append((f"Voz pegada ({vid[:6]}…)", vid))
        self.voice.set("eleven_voices", voices)
        self.nyx._eleven_pick("Voz pegada", vid)       # la guarda y la prueba
        self._eleven_text()

    def _test_mic(self):
        self.mic_status.setText("Escuchando 1,5 segundos... di algo.")
        device = self.mic.currentData()

        def done(result):
            if isinstance(result, Exception):
                self.mic_status.setText(f"No puedo usar ese micro: {result}")
                return
            bars = int(min(1.0, result * 4) * 20)
            self.mic_status.setText(f"Nivel: {'█' * bars}{'·' * (20 - bars)}  " +
                                    ("Te oigo bien." if bars > 4 else "Muy bajito: acércate o sube el volumen del micro."))
        self._run(lambda: voice_mod.mic_level(device), done)

    # ---------- NYX ----------
    def _body(self):
        frame, v = self._section("NYX")
        s = self.voice.settings
        hide = QPushButton("Ocultar")
        hide.clicked.connect(lambda: self.nyx.setVisible(not self.nyx.isVisible()))
        bring = QPushButton("Traer aquí")
        bring.clicked.connect(self.nyx.bring_here)
        perch = QPushButton("Sentarse")
        perch.clicked.connect(self.nyx.zap)
        v.addLayout(self._row(hide, bring, perch, stretch_first=False))

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Tamaño", objectName="dim"))
        self.size_buttons = {}
        for key, text in [("small", "Pequeña"), ("medium", "Mediana"), ("large", "Grande")]:
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, k=key: self._set_size(k))
            self.size_buttons[key] = b
            size_row.addWidget(b)
        v.addLayout(size_row)
        self._mark_size(s.get("size", "medium"))

        idle = QCheckBox("Movimiento en reposo")
        idle.setChecked(s.get("idle_motion", True))
        idle.toggled.connect(lambda val: self.voice.set("idle_motion", val))
        top = QCheckBox("Siempre encima")
        top.setChecked(s.get("always_on_top", True))
        top.toggled.connect(self.nyx.set_always_on_top)
        v.addLayout(self._row(idle, top, stretch_first=False))
        return frame

    def _mark_size(self, key):
        for k, b in self.size_buttons.items():
            b.setProperty("active", "true" if k == key else "false")
            b.style().unpolish(b)
            b.style().polish(b)

    def _set_size(self, key):
        self.nyx.set_size(key)
        self._mark_size(key)

    # ---------- ventana ----------
    def open_near(self, rect):
        from PySide6.QtWidgets import QApplication
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        x = rect.left() - self.width() - 20
        if x < screen.left():
            x = rect.right() + 20
        y = max(screen.top() + 10, min(rect.bottom() - self.height(), screen.bottom() - self.height() - 10))
        self.move(int(max(screen.left() + 10, x)), int(y))
        self.refresh_brain()
        self.show()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.drag is not None:
            self.move(event.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, event):
        self.drag = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
