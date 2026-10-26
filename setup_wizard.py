"""Asistente de primera vez: perfil del usuario, Ollama y modelo."""
import time

from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

import config
import persona
import voice as voice_settings

STYLE = """
QDialog { background: #0c0a14; }
QLabel { color: #ece6f0; }
QLabel#title { color: #ff6b80; font-size: 18pt; font-weight: 700; }
QLabel#muted { color: #9b91a8; }
QComboBox { background: rgba(255, 45, 74, 25); border: 1px solid #5a2a3a; border-radius: 4px;
            color: #ffffff; padding: 6px 8px; }
QComboBox QAbstractItemView { background: #14121a; color: #ece6f0; selection-background-color: #ff2d4a; }
QLineEdit, QPlainTextEdit {
    background: rgba(255, 45, 74, 25); border: 1px solid #5a2a3a; border-radius: 4px;
    color: #ffffff; padding: 6px 8px;
}
QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #ff6b80; }
QPushButton {
    background: #ff2d4a; border: none; border-radius: 4px; color: white; padding: 8px 18px; font-weight: 600;
}
QPushButton:hover { background: #ff5068; }
QPushButton:disabled { background: #5a2a3a; color: #9b91a8; }
QPushButton#ghost { background: transparent; border: 1px solid #5a2a3a; color: #ece6f0; }
QProgressBar { background: #1b1824; border: 1px solid #2a2533; border-radius: 4px; color: white; text-align: center; }
QProgressBar::chunk { background: #ff2d4a; border-radius: 3px; }
"""


class SetupWorker(QThread):
    status = Signal(str)
    progress = Signal(int, int)       # hecho, total (0, 0 = sin barra)
    need_ollama = Signal()
    failed = Signal(str)
    done = Signal()

    def run(self):
        try:
            self.status.emit("Buscando Ollama...")
            if not persona.ollama_running():
                if not persona.start_ollama():
                    self.need_ollama.emit()
                    return
                self.status.emit("Abriendo Ollama...")
                for _ in range(30):
                    if persona.ollama_running():
                        break
                    time.sleep(1)
                else:
                    self.need_ollama.emit()
                    return

            if not persona.has_model(persona.base_model()):
                self.status.emit("Descargando el cerebro de Nyx (unos 6,6 GB). Esto tarda un rato...")

                def report(done, total, text):
                    self.progress.emit(done, total)
                    if total:
                        self.status.emit(f"Descargando el cerebro de Nyx: {done / 1e9:.1f} de {total / 1e9:.1f} GB")
                persona.pull_base(report)

            self.progress.emit(0, 0)
            self.status.emit("Dándole su personalidad...")
            persona.create_model()
            self.done.emit()
        except Exception as e:  # noqa: BLE001 - se enseña tal cual en el asistente
            self.failed.emit(str(e))


class SetupWizard(QDialog):
    def __init__(self, profile_only=False):
        super().__init__()
        self.setWindowTitle("Nyx · Configuración")
        self.setWindowIcon(QIcon(str(config.ICON)))
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(460)
        self.profile_only = profile_only
        self.worker = None

        self.pages = QStackedWidget()
        self.pages.addWidget(self._profile_page())
        self.pages.addWidget(self._install_page())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.addWidget(self.pages)

    # ---------- página 1: perfil ----------
    def _profile_page(self):
        page = QWidget()
        p = config.PROFILE
        title = QLabel("Hola, soy Nyx", objectName="title")
        intro = QLabel("Antes de nada, cuéntame un poco de ti para saber cómo llamarte.", objectName="muted")
        intro.setWordWrap(True)
        self.name = QLineEdit(p.get("name", ""), placeholderText="Tu nombre (p. ej. Alex)")
        self.nick = QLineEdit(p.get("nick", ""), placeholderText="Tu nick (opcional)")
        self.about = QPlainTextEdit(p.get("about", ""))
        self.about.setPlaceholderText("Algo sobre ti: qué estudias, a qué juegas, qué te gusta... (opcional)")
        self.about.setFixedHeight(80)
        self.skin = QComboBox()
        current = voice_settings.load_settings().get("skin", "nyx")
        for sid, (sname, _, _) in config.skins().items():
            self.skin.addItem(sname, sid)
            if sid == current:
                self.skin.setCurrentIndex(self.skin.count() - 1)
        self.next_btn = QPushButton("Guardar" if self.profile_only else "Siguiente")
        self.next_btn.clicked.connect(self._save_profile)
        self.name.textChanged.connect(lambda t: self.next_btn.setEnabled(bool(t.strip())))
        self.next_btn.setEnabled(bool(self.name.text().strip()))

        lay = QVBoxLayout(page)
        lay.setSpacing(10)
        for w in (title, intro, QLabel("Nombre"), self.name, QLabel("Nick"), self.nick,
                  QLabel("Sobre ti"), self.about, QLabel("Apariencia"), self.skin):
            lay.addWidget(w)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.next_btn)
        lay.addLayout(row)
        return page

    def _save_profile(self):
        config.save_profile({"name": self.name.text().strip(), "nick": self.nick.text().strip(),
                             "about": self.about.toPlainText().strip()})
        s = voice_settings.load_settings()
        s["skin"] = self.skin.currentData()
        voice_settings.save_settings(s)
        self.chosen_skin = self.skin.currentData()
        self.pages.setCurrentIndex(1)
        self._start()

    # ---------- página 2: Ollama y modelo ----------
    def _install_page(self):
        page = QWidget()
        title = QLabel("Preparando a Nyx", objectName="title")
        self.status = QLabel("...", wordWrap=True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.help = QLabel(
            "Nyx necesita <b>Ollama</b> para pensar (es gratis). Descárgalo, instálalo y luego pulsa "
            "<b>Reintentar</b>.", wordWrap=True)
        self.help.hide()
        self.download_btn = QPushButton("Descargar Ollama", objectName="ghost")
        self.download_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://ollama.com/download/windows")))
        self.retry_btn = QPushButton("Reintentar", objectName="ghost")
        self.retry_btn.clicked.connect(self._start)
        self.finish_btn = QPushButton("Empezar")
        self.finish_btn.clicked.connect(self.accept)
        for b in (self.download_btn, self.retry_btn, self.finish_btn):
            b.hide()

        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.addWidget(title)
        lay.addWidget(self.status)
        lay.addWidget(self.bar)
        lay.addWidget(self.help)
        row = QHBoxLayout()
        row.addWidget(self.download_btn)
        row.addWidget(self.retry_btn)
        row.addStretch()
        row.addWidget(self.finish_btn)
        lay.addLayout(row)
        lay.addStretch()
        return page

    def _start(self):
        for w in (self.help, self.download_btn, self.retry_btn, self.finish_btn):
            w.hide()
        self.bar.show()
        self.bar.setRange(0, 0)
        self.worker = SetupWorker()
        self.worker.status.connect(self.status.setText)
        self.worker.progress.connect(self._progress)
        self.worker.need_ollama.connect(self._need_ollama)
        self.worker.failed.connect(self._failed)
        self.worker.done.connect(self._done)
        self.worker.start()

    def _progress(self, done, total):
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done / total * 1000))
        else:
            self.bar.setRange(0, 0)

    def _need_ollama(self):
        self.bar.hide()
        self.status.setText("No encuentro Ollama en este ordenador.")
        self.help.show()
        self.download_btn.show()
        self.retry_btn.show()

    def _failed(self, msg):
        self.bar.hide()
        self.status.setText(f"Algo ha fallado: {msg}")
        self.retry_btn.show()

    def _done(self):
        self.bar.hide()
        self.status.setText(f"¡Lista! Ya puedo hablar contigo, {config.nick()}.\n\n"
                            "Haz clic en mí para hablar, arrástrame o lánzame, y clic derecho para ver todo lo que sé hacer.")
        self.finish_btn.show()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()          # no cerrar a mitad de la descarga
        else:
            super().closeEvent(event)
