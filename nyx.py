"""Nyx, compañera de escritorio.

Ejecutar:  .venv\\Scripts\\python.exe nyx.py
- Un clic: abre o cierra el chat (o Ctrl + Alt + N desde cualquier sitio).
- Arrastra para moverla; si la sueltas o la lanzas, cae y se sienta en las ventanas.
- Doble clic: te saluda.
- Clic derecho: menú (poses, Pomodoro, recuerdos, salir).
"""
import math
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QThread, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QInputDialog, QLabel, QLineEdit, QMenu, QSystemTrayIcon,
                               QWidget)

import activity
import config
import memory
import persona
import reminders
import windows
from setup_wizard import SetupWizard
import talk_ui
from bubble import Bubble
from chat import ChatWindow, OneShot
from anim import SpriteAnimations
from effects import ZapEffect
from mainframe import SIZES, Mainframe
from glitch import ScreenGlitch, make_frames
from hotkey import GlobalHotkey
from music import MusicMeter
from pomodoro import Pomodoro
import voice as voice_mod
from voice import VOICES, Voice, headphones_connected

SPRITES = config.SPRITES
HEIGHT = 300                    # altura en píxeles de Nyx de pie
SIT_LINE = 0.53                 # altura (en %) del borde donde se sienta en sit.png
HIP = 0.55                      # altura de la cadera al caer: cuando pasa un borde, se sienta
SLEEP_AFTER_MS = 2 * 60_000     # se duerme tras 2 minutos sin que la toques
BREAK_EVERY_MS = 2 * 3600_000   # te recuerda descansar cada 2 horas
CHATTER_MIN = (25, 45)          # habla sola cada 25-45 minutos
GLITCH_MIN = (20, 50)           # hace una travesura cada 20-50 minutos
WANDER_MIN = (3, 8)             # con "Moverse sola", cambia de sitio cada 3-8 minutos

FRAME_MS = 16                   # física a ~60 fotogramas por segundo
GRAVITY = 1.3
MAX_FALL = 45
BOUNCE = 0.35

# {NAME} y {NICK} se cambian por los del perfil al decirlo (config.personalize)
GREETINGS = {
    "mañana": ["Buenos días, {NICK}. ¿Café y a currar?", "Buenos días, {NAME}. Yo ya llevo un rato en la Red."],
    "tarde": ["Buenas tardes, {NICK}. ¿Qué toca hoy?", "Buenas, {NAME}. Aquí sigo, vigilando tu escritorio."],
    "noche": ["Buenas noches, {NICK}. Mi hora favorita.", "Hola, {NAME}. La noche es nuestra."],
}
WAKE = ["¿Eh? Ah, eras tú. Me había quedado frita.", "Cinco minutos más... Vale, ya estoy.", "Sistema reiniciado. Hola otra vez."]
SLEEP = ["Me echo una siesta. Tócame si me necesitas.", "Modo ahorro de energía activado..."]
THROWN = ["¡Eh! ¡Que no soy una pelota!", "Uf... aterrizaje forzoso.", "Otra vez y te hackeo el ratón.", "¡Wiii! Bueno, no. Para."]
PERCHED = ["Buen sitio. Desde aquí lo vigilo todo.", "Me quedo aquí un rato.", "Qué cómoda es esta ventana."]
ACTIVITY_POLL_MS = 5000          # cada cuánto mira qué ventana tienes delante
ACTIVITY_SETTLE_S = 20           # tiene que durar 20 s para que cuente (no al cambiar de pestaña rápido)
ACTIVITY_COOLDOWN_S = 8 * 60     # como mucho un comentario cada 8 minutos
SAME_CATEGORY_S = 30 * 60        # y no repite tema en media hora
DISTRACTIONS = ("game", "video", "social")
SCOLDS = ["¡Eh! Que estamos en Pomodoro. Eso puede esperar al descanso, {NICK}.",
          "Te estoy viendo, {NAME}. Primero estudiar, luego eso.",
          "¿En serio? Quedan minutos de estudio. Cierra eso, anda.",
          "Pillado. Vuelve al trabajo, {NICK}, que el descanso llega pronto."]
MUSIC_LINES = ["Uh, temazo. No me mires, que bailo fatal.", "Esto suena preem. Súbele.",
               "Música en el escritorio: así sí se trabaja, {NICK}.", "¿Me dejas elegir la siguiente?"]
STUDY_MODE = ("MODO ESTUDIO: sé más seria y concisa. Céntrate en ayudarle a estudiar o a programar, "
              "con pistas claras. Nada de planes de hackeo ni bromas largas.")

EXPRESSIONS = ["think", "laugh", "angry", "surprised"]
EMOTION_POSES = {"normal": "wave", "pensando": "think", "risa": "laugh",
                 "enfadada": "angry", "sorprendida": "surprised"}
PRANKS = ["Je, je. Perdón, se me ha ido la mano con la Red.", "Eso no he sido yo. Bueno, un poco sí.",
          "Pequeño fallo en la Matrix. Ya está arreglado... creo.", "Ups. Interferencias de Night City."]


def part_of_day():
    h = datetime.now().hour
    return "mañana" if 6 <= h < 14 else "tarde" if 14 <= h < 21 else "noche"


class Nyx(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        startup = voice_mod.load_settings()
        self.height_px = SIZES.get(startup.get("size", "medium"), HEIGHT)
        if not startup.get("always_on_top", True):
            self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self._use_skin(startup.get("skin", "nyx"))
        self.mainframe = None
        self.anim_timer = QTimer(self, timeout=self._anim_tick)
        self.anim_name, self.anim_i, self.anim_then = None, 0, None
        self.mouth_on, self.mouth_i = False, 0
        self.poses = self._load_poses()
        self.label = QLabel(self)
        self.pose = None
        self.phase = 0.0
        self.hours_on = 0
        self.tray = None

        # Dónde está apoyada: "floor" (barra de tareas), el hwnd de una ventana, o None (en el aire)
        self.surface = "floor"
        self.perch_rect = None
        self.gravity_on = True
        self.vx = self.vy = 0.0
        self.drag_offset = None
        self.press_pos = None
        self.trail = []

        self.set_pose("idle")
        self._place_on_taskbar()

        self.breath = QTimer(self, interval=40, timeout=self._breathe)
        self.breath.start()
        self.blink_timer = QTimer(self, singleShot=True, timeout=self._blink)
        self._schedule_blink()
        self.physics = QTimer(self, interval=FRAME_MS, timeout=self._step)
        self.zap_fx = ZapEffect()
        self.zapping = False
        self.quiet_glitch = False
        self.perch_watch = QTimer(self, interval=250, timeout=self._watch_perch)

        # Si no la tocas en un rato, se duerme
        self.idle_timer = QTimer(self, singleShot=True, interval=SLEEP_AFTER_MS, timeout=self._fall_asleep)
        self.idle_timer.start()

        # Chat: un clic lo abre (esperamos un poco por si era un doble clic)
        self.chat = ChatWindow()
        self.chat.talking.connect(self._on_talking)
        self.chat.emotion.connect(lambda e: self.express(EMOTION_POSES.get(e, "wave")))
        self.click_timer = QTimer(self, singleShot=True,
                                  interval=QApplication.doubleClickInterval(),
                                  timeout=self.toggle_chat)

        # Interfaz: "terminal" (pastilla + bocadillo de terminal) o "clasica" (ventana de chat)
        self.terminal_ui = voice_mod.load_settings().get("ui", "terminal") == "terminal"
        self.classic_bubble = Bubble()
        self.speech = talk_ui.SpeechBox()
        self.input_box = talk_ui.InputBox()
        self.pill = talk_ui.TalkPill()
        self.bubble = self.speech if self.terminal_ui else self.classic_bubble
        self.input_box.submitted.connect(lambda t: self.chat.send_text(t))
        self.pill.type_clicked.connect(self.open_input)
        self.pill.voice_clicked.connect(self.toggle_voice_chat)
        self.pill.mic_clicked.connect(self._toggle_mute)
        self.chat.sent.connect(lambda t: self.terminal_ui and self.speech.show_exchange(t, self.frameGeometry()))
        self.chat.streamed.connect(lambda p: self.terminal_ui and self.speech.add_reply(p))
        self.chat.finalized.connect(self._on_finalized)
        self.chat.noted.connect(lambda t: self.terminal_ui and self.speech.isVisible() and self.speech.note(t))

        # Bocadillo: saludo al arrancar, descansos y comentarios sueltos
        self.oneshot = None
        QTimer.singleShot(2500, lambda: self.say(random.choice(GREETINGS[part_of_day()])))
        self.break_timer = QTimer(self, interval=BREAK_EVERY_MS, timeout=self._remind_break)
        self.break_timer.start()
        self.chatter_timer = QTimer(self, singleShot=True, timeout=self._chatter)
        self._schedule_chatter()

        # Pomodoro
        self.pomodoro = Pomodoro()
        self.pomodoro.message.connect(self._pomodoro_message)
        self.pomodoro.tick.connect(self._pomodoro_tick)

        # Recordatorios: mira cada 20 segundos si toca avisar de algo
        self.reminder_timer = QTimer(self, interval=20_000, timeout=self._check_reminders)
        self.reminder_timer.start()
        QTimer.singleShot(4000, self._check_reminders)

        # Modo travesura
        self.screen_glitch = ScreenGlitch()
        self.glitch_frames = {}
        self.glitch_left = 0
        self.glitch_anim = QTimer(self, interval=70, timeout=self._glitch_step)
        self.prank_timer = QTimer(self, singleShot=True, timeout=self._random_prank)
        self._schedule_prank()

        # Voz
        self.voice = Voice()
        self.voice.heard.connect(self._voice_heard)
        self.voice.listening.connect(self._voice_listening)
        self.voice.status.connect(self.say)
        self.voice.level.connect(self.pill.set_level)
        self.voice.speaking.connect(lambda on: self._set_mouth(on or self.chat.worker is not None))
        self.voice.busy_check = lambda: self.chat.worker is not None
        self.chat.replied.connect(lambda t: self.voice.speak(t, premium=True))
        self.bg = []                       # hilos sueltos (ElevenLabs: voces, saldo)

        # Qué estás haciendo
        self.activity_now = None          # (categoría, detalle) que ya cuenta
        self.activity_pending = None      # lo que acaba de aparecer, esperando a ver si dura
        self.activity_since = 0.0
        self.last_comment = time.monotonic() - ACTIVITY_COOLDOWN_S + 60   # el primero, al minuto
        self.last_by_category = {}
        self.last_scold = 0.0
        self.activity_timer = QTimer(self, interval=ACTIVITY_POLL_MS, timeout=self._watch_activity)
        self.activity_timer.start()
        self.chat.context = self._chat_context

        # Moverse sola entre ventanas (si está activado)
        self.wander_timer = QTimer(self, singleShot=True, timeout=self._wander)
        self.wander_timer.start(random.randint(*WANDER_MIN) * 60_000)

        # Música: si suena Spotify, baila
        self.music = MusicMeter()
        self.dancing = False
        self.beat = 0.0
        self.last_music_comment = -1e9
        self.music_check = QTimer(self, interval=2000, timeout=self._check_music)
        self.music_check.start()

    # ---------- música ----------
    def _check_music(self):
        if not self.voice.settings.get("dance", True):
            self.dancing = False
            return
        playing = self.music.refresh()
        if playing and not self.dancing and time.monotonic() - self.last_music_comment > 30 * 60:
            self.last_music_comment = time.monotonic()
            QTimer.singleShot(3000, lambda: self.dancing and self.say(random.choice(MUSIC_LINES)))
        self.dancing = playing

    def _dance_offset(self):
        """Salto según el volumen: sube rápido con cada golpe y baja suave."""
        level = self.music.level()
        # Se adapta al volumen: compara con lo más fuerte que ha sonado últimamente
        self.loudest = max(level, getattr(self, "loudest", 0.05) * 0.997, 0.02)
        self.average = getattr(self, "average", level) * 0.9 + level * 0.1
        hit = max(0.0, (level - self.average * 0.8) / self.loudest)   # golpes por encima de la media
        self.beat = max(min(1.0, hit * 1.6), self.beat * 0.8)
        self.phase += 0.12
        return int(-self.beat * 14), int(3 * math.sin(self.phase))

    # ---------- qué estás haciendo ----------
    @property
    def study_mode(self):
        return self.voice.settings.get("mode") == "estudio"

    def _set_mode(self, mode):
        self.voice.set("mode", mode)
        self.say("Modo estudio activado. Me pongo seria, {NAME}." if mode == "estudio"
                 else "Modo charla. Ya puedo volver a ser yo, {NICK}.")

    def _chat_context(self):
        parts = []
        if self.activity_now and self.voice.settings.get("activity", True):
            parts.append(f"Ahora mismo {config.name()} {activity.describe(*self.activity_now)}.")
        if self.study_mode:
            parts.append(STUDY_MODE)
        return " ".join(parts)

    def _watch_activity(self):
        info = activity.foreground()
        found = activity.classify(info)
        if found is None:
            return
        now = time.monotonic()
        key = (found[0], found[1][:40])
        if self.activity_pending is None or self.activity_pending[0] != key:
            self.activity_pending = (key, found, info[3])
            self.activity_since = now
            return
        if now - self.activity_since < ACTIVITY_SETTLE_S or (self.activity_now and self.activity_now[0] == found[0]
                                                            and self.activity_now[1][:40] == found[1][:40]):
            return
        self.activity_now = found
        self._react(found, fullscreen=self.activity_pending[2])

    def _react(self, found, fullscreen):
        cat, detail = found
        now = time.monotonic()
        busy = self._in_conversation() or self.pose == "sleep" or fullscreen or self.oneshot is not None

        # En Pomodoro (estudiando), las distracciones se riñen siempre
        if self.pomodoro.running and self.pomodoro.phase == "work" and cat in DISTRACTIONS:
            if now - self.last_scold > 180 and not fullscreen:
                self.last_scold = now
                self.express("angry", 4000)
                self.say(random.choice(SCOLDS))
            return

        if busy or not self.voice.settings.get("activity", True) or self.pomodoro.running:
            return
        if self.study_mode and cat not in DISTRACTIONS:
            return          # en modo estudio solo comenta si te distraes
        if now - self.last_comment < ACTIVITY_COOLDOWN_S or now - self.last_by_category.get(cat, -1e9) < SAME_CATEGORY_S:
            return
        self.last_comment = now
        self.last_by_category[cat] = now
        self.oneshot = OneShot(
            f"Te acabas de dar cuenta de que {config.name()} {activity.describe(cat, detail)}. "
            "Coméntaselo en UNA frase corta y natural (máximo 18 palabras), como una amiga que mira por encima del hombro. "
            "Sin saludar.", STUDY_MODE if self.study_mode else "")
        self.oneshot.result.connect(self.say)
        self.oneshot.finished.connect(lambda: setattr(self, "oneshot", None))
        self.oneshot.start()

    # ---------- voz ----------
    def listen(self):
        self._touched(quiet=True)
        self.voice.start_listening()

    def _voice_listening(self, active):
        if self.voice.conversation or (not active and self.terminal_ui and self.speech.busy()):
            return               # en conversación, lo enseñan las ondas de la pastilla
        if active:
            self.bubble.say("🎙️ Te escucho... (suelta para enviar)", self.frameGeometry(), ms=30000)
        else:
            self.bubble.hide()

    def _voice_heard(self, text):
        if self.terminal_ui:
            self.chat.send_text(text)
            return
        if not self.chat.isVisible():
            self.bubble.hide()
            self.chat.show_near(self.frameGeometry())
        self.chat.send_text(text)

    def toggle_voice_chat(self):
        """Botón de las ondas: conversación por voz (escucha sola y contesta hablando)."""
        self._touched(quiet=True)
        if self.voice.conversation:
            self.voice.stop_conversation()
            self.pill.set_voice_mode(False)
            self.speech.say("Fin de la llamada. Escríbeme si me necesitas.", self.frameGeometry(), ms=3000)
        else:
            self.voice.start_conversation()
            if self.voice.conversation:
                self.pill.set_voice_mode(True)
                self.pill.set_muted(False)
                self.speech.say("Te escucho. Habla cuando quieras, y para cuando acabes.",
                                self.frameGeometry(), ms=4000)
        self._follow_ui()

    def _toggle_mute(self):
        self.pill.set_muted(self.voice.toggle_mute())

    # ---------- interfaz ----------
    def _in_conversation(self):
        """¿Estás hablando con ella ahora mismo? (entonces no interrumpe con comentarios)"""
        if self.chat.isVisible():
            return True
        return self.terminal_ui and (self.speech.busy() or self.input_box.isVisible() or self.voice.conversation)

    def open_input(self):
        if self.input_box.isVisible():
            self.input_box.glitch(250, then_hide=True)
            return
        screen = QApplication.primaryScreen().availableGeometry()
        x = min(self.pill.x(), screen.right() - self.input_box.width() - 8)
        y = self.pill.y() - self.input_box.height() - 16
        if y < screen.top():
            y = self.pill.y() + self.pill.height() + 16
        self.input_box.open_at(max(screen.left() + 8, x), y)

    def _on_finalized(self, text):
        if self.terminal_ui:
            if text:
                self.speech.set_reply(text)
            self.speech.finish()

    def set_ui(self, mode):
        self.voice.set("ui", mode)
        self.terminal_ui = mode == "terminal"
        self.bubble.hide()
        self.bubble = self.speech if self.terminal_ui else self.classic_bubble
        if self.terminal_ui:
            self.chat.hide()
            self.pill.show()
            self._follow_ui()
        else:
            self.pill.hide()
            self.input_box.hide()
            if self.voice.conversation:
                self.toggle_voice_chat()

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "terminal_ui", False):
            self.pill.show()
            self._follow_ui()

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, "pill"):
            for w in (self.pill, self.speech, self.input_box):
                w.hide()

    def _toggle_voice(self, on):
        self.voice.set("voice_on", on)
        if on and self.voice.settings["only_headphones"] and not headphones_connected():
            self.say("Voz activada, pero no veo cascos conectados. Hablaré cuando te los pongas.")
        elif on:
            self.say("Voz activada. Ahora me oyes, {NICK}.")

    # ---------- ElevenLabs ----------
    def _in_background(self, fn, done):
        """Ejecuta fn() en otro hilo (llamadas a internet) y luego done(resultado o excepción)."""
        class Job(QThread):
            finished_with = Signal(object)

            def run(self_job):
                try:
                    self_job.finished_with.emit(fn())
                except Exception as e:  # noqa: BLE001
                    self_job.finished_with.emit(e)
        job = Job()
        job.finished_with.connect(done)
        job.finished.connect(lambda: self.bg.remove(job))
        self.bg.append(job)
        job.start()

    def _eleven_setup(self):
        key, ok = QInputDialog.getText(None, "ElevenLabs", "Pega tu clave de ElevenLabs (API key).\n"
                                       "Se guarda solo en este ordenador:", QLineEdit.Password,
                                       self.voice.settings.get("eleven_key", ""))
        if not ok or not key.strip():
            return
        key = key.strip()
        self.say("Comprobando la clave...")

        def done(result):
            if isinstance(result, Exception):
                self.say("Esa clave no me funciona. Revisa que la has copiado entera.")
                return
            self.voice.set("eleven_key", key)
            self.voice.set("eleven_voices", result)
            self.voice.set("eleven_on", True)
            if result and not self.voice.settings.get("eleven_voice"):
                self.voice.set("eleven_voice", result[0][1])
            self.say(f"Listo. Tengo {len(result)} voces de ElevenLabs. Elige una en Voz > ElevenLabs.")
        self._in_background(lambda: voice_mod.eleven_voices(key), done)

    def _eleven_pick(self, name, voice_id):
        self.voice.set("eleven_voice", voice_id)
        self.voice.set("eleven_on", True)
        text = config.personalize("¿Qué tal suena esta voz, {NICK}? Soy Nyx, desde la Red.")
        self.bubble.say(text, self.frameGeometry())
        self.voice.preview(text, premium=True)

    def _eleven_balance(self):
        key = self.voice.settings.get("eleven_key")
        if not key:
            return

        def done(result):
            if isinstance(result, Exception):
                if "401" in str(result):
                    self.say("Tu clave no tiene permiso para ver el saldo (user_read). Míralo en la web de ElevenLabs.")
                else:
                    self.say("No he podido mirar el saldo. ¿Hay internet?")
                return
            used, limit = result
            self.say(f"ElevenLabs: llevas {used} de {limit} caracteres este mes. Te quedan {max(0, limit - used)}.")
        self._in_background(lambda: voice_mod.eleven_left(key), done)

    def _choose_voice(self, name):
        self.voice.set("voice", name)
        text = config.personalize("¿Qué tal suena esta voz, {NICK}? Soy Nyx, desde la Red.")
        self.bubble.say(text, self.frameGeometry())
        self.voice.preview(text)          # se oye siempre, para poder elegir

    # ---------- recordatorios ----------
    def _check_reminders(self):
        for r in reminders.pop_due():
            self._touched(quiet=True)
            self.wave()
            text = f"¡Eh, {config.nick()}! Te recuerdo: {r['texto']}"
            if self.chat.isVisible() or (self.terminal_ui and self.speech.busy()):
                self.chat.note(text)
            else:
                self.bubble.say(text, self.frameGeometry(), ms=15000)
            if self.tray:
                self.tray.showMessage("Nyx", text, QSystemTrayIcon.Information, 10000)

    def edit_profile(self):
        wizard = SetupWizard(profile_only=True)
        if wizard.exec() == SetupWizard.Accepted:
            self.voice.settings = voice_mod.load_settings()     # el asistente ha podido cambiar la apariencia
            if getattr(wizard, "chosen_skin", self.skin_id) != self.skin_id:
                self.set_skin(wizard.chosen_skin)
            else:
                self.say("Perfil actualizado. Encantada otra vez, {NICK}.")

    def show_reminders(self):
        memory.DATA.mkdir(exist_ok=True)
        notes = memory.DATA / "recordatorios.txt"
        items = reminders.load()
        lines = [f"- {r['cuando']}  ·  {r['texto']}" for r in items] or ["(no tienes ninguno)"]
        notes.write_text("Recordatorios pendientes:\n\n" + "\n".join(lines) +
                         "\n\nPara añadir uno, díselo a Nyx en el chat: «recuérdame ... el jueves a las 10».\n",
                         encoding="utf-8")
        os.startfile(notes)

    # ---------- travesuras ----------
    def _schedule_prank(self):
        self.prank_timer.start(random.randint(*GLITCH_MIN) * 60_000)

    def _random_prank(self):
        self._schedule_prank()
        if self.pose != "sleep" and not self._in_conversation() and not self.pomodoro.running and not self.study_mode:
            self.prank()

    def prank(self):
        if self.anims:
            # Las apariencias animadas traen su propia animación de glitch
            self.play("sit_glitch" if self.pose == "sit" and self.anims.has("sit_glitch") else "glitch")
            self.screen_glitch.play()
            QTimer.singleShot(1200, lambda: self.say(random.choice(PRANKS)))
            return
        if self.glitch_left:
            return
        if self.pose not in self.glitch_frames:
            size = self.poses[self.pose].size()
            self.glitch_frames[self.pose] = make_frames(self.skin_dir / f"{self.pose}.png",
                                                        (size.width(), size.height()))
        self.glitch_left = 14
        self.glitch_anim.start()
        self.screen_glitch.play()

    def _glitch_step(self):
        self.glitch_left -= 1
        frames = self.glitch_frames.get(self.pose)
        if self.glitch_left <= 0 or not frames:
            self.glitch_anim.stop()
            self.glitch_left = 0
            self.label.setPixmap(self.poses[self.pose])
            self.label.resize(self.poses[self.pose].size())
            self.label.move(0, 2)
            if not self.quiet_glitch:
                self.say(random.choice(PRANKS))
            self.quiet_glitch = False
            return
        # Alterna entre fotogramas rotos y el normal, temblando un poco
        if random.random() < 0.7:
            pix = random.choice(frames)
            self.label.setPixmap(pix)
            self.label.resize(pix.size())
            self.label.move(-8 + random.randint(-4, 4), random.randint(0, 4))
        else:
            self.label.setPixmap(self.poses[self.pose])
            self.label.resize(self.poses[self.pose].size())
            self.label.move(random.randint(-3, 3), 2)

    # ---------- bocadillo ----------
    def say(self, text):
        text = config.personalize(text)
        if self.isVisible() and not self.chat.isVisible() and not (self.terminal_ui and self.speech.busy()):
            self.bubble.say(text, self.frameGeometry())
            if hasattr(self, "voice"):
                self.voice.speak(text)

    def _remind_break(self):
        self.hours_on += BREAK_EVERY_MS // 3600_000
        if not self.pomodoro.running:
            self.say(f"Llevas {self.hours_on} horas con el ordenador, {config.nick()}. Levántate y estira un poco.")

    def _schedule_chatter(self):
        self.chatter_timer.start(random.randint(*CHATTER_MIN) * 60_000)

    def _chatter(self):
        self._schedule_chatter()
        if self.pose == "sleep" or self._in_conversation() or self.oneshot is not None or self.pomodoro.running \
                or self.study_mode:
            return
        self.oneshot = OneShot(f"Di a {config.name()} UNA sola frase corta y espontánea, como si te acordaras de algo "
                               "que sabes de él, comentaras la hora o le preguntaras qué tal va. "
                               "Sin saludar. Máximo 20 palabras.")
        self.oneshot.result.connect(self.say)
        self.oneshot.finished.connect(lambda: setattr(self, "oneshot", None))
        self.oneshot.start()

    # ---------- Pomodoro ----------
    def _pomodoro_message(self, text):
        self._touched(quiet=True)
        self.say(text)
        self.wave()

    def _pomodoro_tick(self, text):
        tip = f"Nyx  ·  {text}" if text else "Nyx  ·  Ctrl+Alt+N para hablar"
        self.setToolTip(text)
        if self.tray:
            self.tray.setToolTip(tip)

    # ---------- chat ----------
    def toggle_chat(self):
        if self.terminal_ui:
            self.open_input()
            return
        if self.chat.isVisible():
            self.chat.hide()
        else:
            self.bubble.hide()
            self.chat.show_near(self.frameGeometry())

    def open_chat_from_hotkey(self):
        if not self.isVisible():
            self.show()
        self._touched()
        self.toggle_chat()

    def _on_talking(self, active):
        self._touched(quiet=True)
        self._set_mouth(active or self.voice.player.playbackState() == self.voice.player.PlaybackState.PlayingState)
        if active and self.anims:
            if self.pose not in ("idle", "sit"):
                self.set_pose("idle")             # animada: habla moviendo la boca, sin cambiar de pose
        elif active:
            self.set_pose("wave")
        else:
            # Mantiene la cara un poco después de contestar
            pose = self.pose
            QTimer.singleShot(4000, lambda: self.pose == pose and not self.chat.worker
                              and self.drag_offset is None and self.set_pose("idle"))

    def show_memories(self):
        memory.DATA.mkdir(exist_ok=True)
        notes = memory.DATA / "recuerdos.txt"
        facts = memory.load_facts()
        notes.write_text("Lo que Nyx recuerda de ti:\n\n" + ("\n".join(f"- {f}" for f in facts) or "(todavía nada)"),
                         encoding="utf-8")
        os.startfile(notes)

    # ---------- poses ----------
    # ---------- Mainframe ----------
    def open_mainframe(self):
        if self.mainframe is None:
            self.mainframe = Mainframe(self)
        self.mainframe.open_near(self.frameGeometry())

    def set_size(self, key):
        self.voice.set("size", key)
        self.height_px = SIZES.get(key, HEIGHT)
        self.poses = self._load_poses()
        self.glitch_frames = {}
        self.set_pose("sleep" if self.pose == "sleep" else "idle")
        self._follow_ui()

    def set_always_on_top(self, on):
        self.voice.set("always_on_top", on)
        for w in (self, self.pill, self.speech):
            visible = w.isVisible()
            w.setWindowFlag(Qt.WindowStaysOnTopHint, on)
            if visible:
                w.show()

    def bring_here(self):
        """Trae a Nyx a donde está el ratón (y cae desde ahí)."""
        pos = QCursor.pos()
        self.show()
        self.move(pos.x() - self.width() // 2, pos.y() - self.height() // 2)
        self._start_fall()

    # ---------- apariencias ----------
    def _use_skin(self, skin_id):
        all_skins = config.skins()
        if skin_id not in all_skins:
            skin_id = "nyx"
        self.skin_id = skin_id
        _, self.skin_dir, self.sit_line = all_skins[skin_id]
        self.skin_meta = config.skin_meta(skin_id) if skin_id != "nyx" else {}

    # ---------- animaciones (apariencias animadas) ----------
    def play(self, name, then=None):
        """Reproduce una animación. Si no se repite, al acabar llama a then() (o vuelve a la de la pose)."""
        if not self.anims or not self.anims.has(name):
            return
        self.anim_name, self.anim_i, self.anim_then = name, 0, then
        self.anim_timer.start(int(1000 / self.anims.fps(name)))
        self._show_frame()

    def _back_to_pose(self):
        base = self.anims.pose_anim(self.pose) if self.anims else None
        if base:
            self.play(base)

    def _anim_tick(self):
        frames = self.anims.frames.get(self.anim_name) if self.anims else None
        if not frames:
            self.anim_timer.stop()
            return
        self.anim_i += 1
        self.mouth_i += 1
        if self.anim_i >= len(frames):
            if self.anims.loops(self.anim_name):
                self.anim_i = 0
            else:
                then, self.anim_then = self.anim_then, None
                (then or self._back_to_pose)()
                return
        self._show_frame()

    def _show_frame(self):
        frame = self.anims.frames[self.anim_name][self.anim_i]
        if self.mouth_on and self.anim_name == "idle":
            frame = self.anims.with_overlay(frame, "mouth", self.mouth_i)
        self.label.setPixmap(frame)

    def _set_mouth(self, on):
        self.mouth_on = on

    def set_skin(self, skin_id):
        self._use_skin(skin_id)
        self.voice.set("skin", self.skin_id)
        self.poses = self._load_poses()
        self.glitch_frames = {}
        self.set_pose("sleep" if self.pose == "sleep" else "idle")
        self.prank()                     # el cambio, con efecto glitch
        self.say("¿Qué tal mi nuevo look, {NICK}?")

    def _load_poses(self):
        poses = {}
        sprites = self.skin_dir
        self.anims = None
        if self.skin_meta.get("animated"):
            self.anims = SpriteAnimations(sprites, self.skin_meta, self.height_px)
            for pose, anim_name in self.skin_meta.get("poses", {}).items():
                if self.anims.has(anim_name):
                    poses[pose] = self.anims.first(anim_name)
            return poses
        stand = QPixmap(str(sprites / "idle.png"))
        scale = self.height_px / stand.height()      # todas las poses a la misma escala
        names = ["idle", "wave", "sleep", "sit"]
        names += [f"{n}_blink" for n in names if (sprites / f"{n}_blink.png").exists()]
        for name in names:
            pix = QPixmap(str(sprites / f"{name}.png"))
            if pix.isNull():
                pix = QPixmap(str(sprites / "idle.png"))     # si a una apariencia le falta una pose
            poses[name] = pix.scaled(int(pix.width() * scale), int(pix.height() * scale),
                                     Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # Las expresiones vienen de otra hoja, dibujada a otro tamaño: se escalan con la suya
        think = sprites / "think.png"
        if think.exists():
            expr_scale = self.height_px / QPixmap(str(think)).height()
            for name in EXPRESSIONS:
                pix = QPixmap(str(sprites / f"{name}.png"))
                if not pix.isNull():
                    poses[name] = pix.scaled(int(pix.width() * expr_scale), int(pix.height() * expr_scale),
                                             Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return poses

    def express(self, name, ms=None):
        """Pone una cara un rato y luego vuelve a estar normal."""
        if name not in self.poses:
            return
        self.set_pose(name)
        if ms:
            QTimer.singleShot(ms, lambda: self.pose == name and self.drag_offset is None
                              and self.surface is not None and self.set_pose("idle"))

    def _schedule_blink(self):
        # A veces parpadea dos veces seguidas, como la gente
        self.blink_timer.start(random.choice([150, 2500, 3500, 4500, 6000]))

    def _blink(self):
        self._schedule_blink()
        if self.anims:
            if self.drag_offset is None and self.anim_name in ("idle", "sit") and \
                    self.anims.has("blink" if self.anim_name == "idle" else "sit_blink"):
                self.play("blink" if self.anim_name == "idle" else "sit_blink")
            return
        closed = self.poses.get(f"{self.pose}_blink")
        if closed is None or self.glitch_left or self.drag_offset is not None:
            return
        self.label.setPixmap(closed)
        QTimer.singleShot(130, lambda p=self.pose: self.pose == p and not self.glitch_left
                          and self.label.setPixmap(self.poses[p]))

    def set_pose(self, name):
        # Encima de una ventana, "de pie" se convierte en "sentada"
        if name == "idle" and self._on_window():
            name = "sit"
        center = self.x() + self.width() // 2
        pix = self.poses[name]
        self.pose = name
        self.label.setPixmap(pix)
        self.label.resize(pix.size())
        self.resize(pix.size().width(), pix.size().height() + 4)
        self.move(center - self.width() // 2, self.y())
        self._snap_to_surface()
        base = self.anims.pose_anim(name) if self.anims else None
        if base:
            self.play(base)
        else:
            self.anim_timer.stop()

    def wave(self):
        self.set_pose("wave")
        QTimer.singleShot(2500, lambda: self.pose == "wave" and not self.chat.worker and self.set_pose("idle"))

    def _fall_asleep(self):
        if self._in_conversation() or self.surface is None:
            self.idle_timer.start()
            return
        self.say(random.choice(SLEEP))
        self.set_pose("sleep")

    def _touched(self, quiet=False):
        self.idle_timer.start()
        if self.pose == "sleep":
            self.set_pose("idle")
            if self.anims and self.anims.has("wake") and not self._on_window():
                self.play("wake")                 # se despierta "arrancando el sistema"
            if not quiet:
                self.say(random.choice(WAKE))

    def _breathe(self):
        if self.drag_offset is not None or self.surface is None or self.glitch_left:
            return
        if getattr(self, "dancing", False) and self.pose != "sleep":
            jump, sway = self._dance_offset()
            rest = self._rest_y()
            if rest is not None:
                self.move(self.x(), rest + jump)      # salta la ventana entera (así no se corta el pelo)
            self.label.move(sway, 2)
            self.was_dancing = True
            return
        if getattr(self, "was_dancing", False):
            self.was_dancing = False
            self._snap_to_surface()
        if not self.voice.settings.get("idle_motion", True) if hasattr(self, "voice") else False:
            self.label.move(0, 2)
            return
        speed = 0.04 if self.pose == "sleep" else 0.08
        self.phase += speed
        self.label.move(0, int(2 + 2 * math.sin(self.phase)))

    # ---------- superficies ----------
    def _on_window(self):
        return isinstance(self.surface, int)

    def _dpr(self):
        return self.screen().devicePixelRatio() if self.screen() else 1.0

    def _floor_y(self):
        return QApplication.primaryScreen().availableGeometry().bottom() + 1

    def _surface_y(self):
        """Altura (lógica) de la línea donde está apoyada."""
        if self.surface == "floor":
            return self._floor_y()
        if self.perch_rect:
            return self.perch_rect[1] / self._dpr()
        return None

    def _rest_y(self):
        """Altura de la ventana para estar apoyada en su superficie, o None si está en el aire."""
        top = self._surface_y()
        if top is None:
            return None
        if self.pose == "sit":
            return int(top - int(self.sit_line * self.label.height()) - 2)
        return int(top - self.height() + 2)

    def _snap_to_surface(self):
        y = self._rest_y()
        if y is None:
            return
        self.move(self.x(), y)
        self._follow_ui()

    def _place_on_taskbar(self):
        area = QApplication.primaryScreen().availableGeometry()
        self.move(area.right() - self.width() - 80, self.y())
        self.surface = "floor"
        self._snap_to_surface()

    def _follow_ui(self):
        if hasattr(self, "pill") and self.terminal_ui:
            rect = self.frameGeometry()
            self.pill.follow(rect)
            self.speech.follow(rect)
        if hasattr(self, "chat") and self.chat.isVisible():
            self.chat.show_near(self.frameGeometry())

    def _watch_perch(self):
        """Si la ventana donde está sentada se mueve, la sigue; si se cierra, se cae."""
        if not self._on_window():
            self.perch_watch.stop()
            return
        rect = windows.window_rect(self.surface)
        if rect is None:
            self._start_fall()
            return
        if rect != self.perch_rect:
            dpr = self._dpr()
            dx = (rect[0] - self.perch_rect[0]) / dpr
            self.perch_rect = rect
            self.move(int(self.x() + dx), self.y())
            self._snap_to_surface()
            # Si la ventana se ha ido de debajo, se cae
            cx = (self.x() + self.width() / 2) * dpr
            if not (rect[0] <= cx <= rect[2]):
                self._start_fall()

    # ---------- teletransporte ----------
    def _pick_target(self):
        """(superficie, rect, x del centro, línea donde apoyarse) de un sitio nuevo al que ir."""
        dpr = self._dpr()
        options = [o for o in windows.ledges() if o[0] != self.surface]
        if options:
            hwnd, rect, xs = random.choice(options)
            return hwnd, rect, random.choice(xs) / dpr, rect[1] / dpr
        area = QApplication.primaryScreen().availableGeometry()
        return "floor", None, random.randint(area.left() + 150, area.right() - 150), self._floor_y()

    def zap(self):
        """Teletransporte: se deshace en glitch, vuela como un rayo y se materializa en otra ventana."""
        if self.zapping or self.drag_offset is not None:
            return
        self._touched(quiet=True)
        self.zapping = True
        surface, rect, tx, line = self._pick_target()
        start = self.frameGeometry().center()
        end = QPoint(int(tx), int(line - 90 if surface != "floor" else line - self.height() * 0.6))
        self.bubble.hide()

        def leave():
            self.physics.stop()
            self.perch_watch.stop()
            self.setWindowOpacity(0.0)          # invisible mientras vuela (sin cerrar la ventana)

        def arrive():
            self.surface, self.perch_rect = surface, (windows.window_rect(surface) or rect) if surface != "floor" else None
            self.set_pose("idle")               # en una ventana se convierte en "sentada"
            self.move(int(tx - self.width() / 2), self.y())
            self._snap_to_surface()
            self.setWindowOpacity(1.0)
            self._glitch_visual()
            if self._on_window():
                self.perch_watch.start()

        def done():
            self.zapping = False

        self._glitch_visual()
        self.zap_fx.play(start, end, leave, arrive, done)

    def _glitch_visual(self):
        """Solo el parpadeo de glitch de la figura (sin interferencias en pantalla ni frase)."""
        if self.anims:
            self.play("sit_glitch" if self.pose == "sit" and self.anims.has("sit_glitch") else "glitch")
            return
        if self.pose not in self.glitch_frames:
            size = self.poses[self.pose].size()
            self.glitch_frames[self.pose] = make_frames(self.skin_dir / f"{self.pose}.png",
                                                        (size.width(), size.height()))
        self.glitch_left = 6
        self.glitch_anim.start()
        self.quiet_glitch = True

    def _wander(self):
        self.wander_timer.start(random.randint(*WANDER_MIN) * 60_000)
        if self.voice.settings.get("wander", False) and self.pose != "sleep" and not self._in_conversation() \
                and not self.pomodoro.running and self.surface is not None:
            self.zap()

    # ---------- física ----------
    def _start_fall(self, vx=0.0, vy=0.0):
        self.surface = None
        self.perch_rect = None
        self.perch_watch.stop()
        if self.pose in ("sit", "sleep"):
            self.set_pose("idle")
        self.label.move(0, 2)
        self.vx, self.vy = vx, vy
        self.physics.start()

    def _land(self, surface, rect=None, thrown=False):
        self.physics.stop()
        self.vx = self.vy = 0
        self.surface = surface
        self.perch_rect = rect
        self.set_pose("idle")        # en una ventana se convierte en "sit"
        if self._on_window():
            self.perch_watch.start()
            if not thrown and random.random() < 0.3:
                self.say(random.choice(PERCHED))
        if thrown:
            if not self._on_window():
                self.express("angry", 3000)
            self.say(random.choice(THROWN))

    def _step(self):
        screen = QApplication.primaryScreen().geometry()
        dpr = self._dpr()
        old_hip = self.y() + HIP * self.height()

        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        self.vx *= 0.99
        x = self.x() + self.vx
        y = self.y() + self.vy

        # Paredes y techo
        if x < screen.left():
            x, self.vx = screen.left(), -self.vx * BOUNCE
        if x + self.width() > screen.right():
            x, self.vx = screen.right() - self.width(), -self.vx * BOUNCE
        if y < screen.top():
            y, self.vy = screen.top(), 0
        self.move(int(x), int(y))

        thrown = abs(self.vx) > 8 or self.vy > 25
        # ¿Pasa por encima de una ventana? Se sienta
        if self.vy > 0:
            new_hip = y + HIP * self.height()
            cx = (x + self.width() / 2) * dpr
            hit = windows.ledge_below(cx, old_hip * dpr, new_hip * dpr)
            if hit:
                hwnd, _ = hit
                self._land(hwnd, windows.window_rect(hwnd), thrown)
                return

        # Suelo (barra de tareas)
        floor = self._floor_y()
        if y + self.height() >= floor:
            if self.vy > 18:
                self.move(int(x), floor - self.height())
                self.vy = -self.vy * BOUNCE    # rebotito
                self.vx *= 0.7
                return
            self._land("floor", thrown=thrown)

    # ---------- ratón ----------
    def mousePressEvent(self, event):
        self._touched()
        if event.button() == Qt.LeftButton:
            self.physics.stop()
            self.press_pos = event.globalPosition().toPoint()
            self.drag_offset = self.press_pos - self.pos()
            self.trail = [(time.monotonic(), self.press_pos)]

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            pos = event.globalPosition().toPoint()
            # Al cogerla en brazos se sorprende
            if self.pose != "surprised" and "surprised" in self.poses and \
                    (pos - self.press_pos).manhattanLength() > 8:
                center_x = self.x() + self.width() // 2
                self.surface = None
                self.perch_watch.stop()
                self.set_pose("surprised")
                self.move(center_x - self.width() // 2, self.y())
                self.drag_offset = pos - self.pos()
            self.move(pos - self.drag_offset)
            self.trail = [p for p in self.trail if time.monotonic() - p[0] < 0.08] + [(time.monotonic(), pos)]
            self.bubble.hide()
            self._follow_ui()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self.press_pos is None:
            return
        pos = event.globalPosition().toPoint()
        moved = (pos - self.press_pos).manhattanLength() > 4
        self.drag_offset = None
        self.press_pos = None
        if not moved:
            self.click_timer.start()
            return
        if not self.gravity_on:
            self.surface = "free"
            self.set_pose("idle")
            return
        # Velocidad del lanzamiento según los últimos movimientos del ratón
        (t0, p0), (t1, p1) = self.trail[0], self.trail[-1]
        dt = max(t1 - t0, 0.001)
        vx = max(-60, min(60, (p1.x() - p0.x()) / dt * FRAME_MS / 1000))
        vy = max(-60, min(60, (p1.y() - p0.y()) / dt * FRAME_MS / 1000))
        self._start_fall(vx, vy)

    def mouseDoubleClickEvent(self, event):
        self.click_timer.stop()
        self._touched()
        self.wave()

    def contextMenuEvent(self, event):
        """Menú corto como el de capri-desktop; los ajustes, agrupados en submenús."""
        self._touched()
        menu = talk_ui.neon_menu(self)

        def check(parent, text, checked, on_toggle):
            a = parent.addAction(text)
            a.setCheckable(True)
            a.setChecked(checked)
            a.toggled.connect(on_toggle)
            return a

        def choices(parent, title, options, current, pick):
            sub = talk_ui.neon_menu(parent, title)
            for key, text in options:
                a = sub.addAction(text)
                a.setCheckable(True)
                a.setChecked(key == current)
                a.triggered.connect(lambda _=False, k=key: pick(k))
            return sub

        # --- lo de siempre ---
        menu.addAction("Hablar con ella", self.toggle_chat)
        menu.addAction("Teletransportarse", self.zap)
        menu.addAction("Volver a la barra de tareas", self._place_on_taskbar)
        menu.addAction("Saludar", self.wave)
        check(menu, "Moverse sola", self.voice.settings.get("wander", False), lambda v: self.voice.set("wander", v))
        menu.addSeparator()
        menu.addAction("Parar Pomodoro" if self.pomodoro.running else "Pomodoro (25 + 5)",
                       self.pomodoro.stop if self.pomodoro.running else self.pomodoro.start)
        menu.addAction("Hacer una travesura", self.prank)

        poses = talk_ui.neon_menu(menu, "Poses")
        for name, text in [("idle", "De pie"), ("sit", "Sentarse"), ("sleep", "Dormir")]:
            poses.addAction(text, lambda n=name: self.set_pose(n))
        if any(f in self.poses for f in EXPRESSIONS):
            poses.addSeparator()
            for name, text in [("think", "Pensativa"), ("laugh", "Riéndose"), ("angry", "Enfadada"),
                               ("surprised", "Sorprendida")]:
                poses.addAction(text, lambda n=name: self.express(n, 4000)).setEnabled(name in self.poses)
        menu.addMenu(poses)
        menu.addSeparator()

        # --- ajustes ---
        menu.addAction("Mainframe (ajustes)", self.open_mainframe)
        settings = talk_ui.neon_menu(menu, "Más ajustes")
        settings.addMenu(choices(settings, "Apariencia", [(k, v[0]) for k, v in config.skins().items()],
                                 self.skin_id, self.set_skin))
        settings.addMenu(choices(settings, "Interfaz", [("terminal", "Terminal (pastilla y bocadillo)"),
                                                        ("clasica", "Clásica (ventana de chat)")],
                                 "terminal" if self.terminal_ui else "clasica", self.set_ui))
        settings.addMenu(choices(settings, "Modo", [("charla", "Charla (normal)"), ("estudio", "Estudio (seria)")],
                                 self.voice.settings.get("mode") or "charla", self._set_mode))
        vmenu = talk_ui.neon_menu(settings, "Voz")
        settings.addMenu(vmenu)
        settings.addSeparator()
        check(settings, "Gravedad", self.gravity_on, self._set_gravity)
        check(settings, "Fijarse en lo que hago", self.voice.settings.get("activity", True),
              lambda v: self.voice.set("activity", v))
        check(settings, "Bailar con la música", self.voice.settings.get("dance", True),
              lambda v: self.voice.set("dance", v))
        settings.addSeparator()
        settings.addAction("Cambiar mi perfil", self.edit_profile)
        menu.addMenu(settings)

        mem = talk_ui.neon_menu(menu, "Memoria")
        mem.addAction("Ver conversación completa", lambda: self.chat.show_near(self.frameGeometry()))
        mem.addAction("Ver recordatorios", self.show_reminders)
        mem.addAction("Ver recuerdos", self.show_memories)
        mem.addSeparator()
        mem.addAction("Borrar memoria", self.chat.forget)
        menu.addMenu(mem)
        menu.addSeparator()
        menu.addAction("Salir", QApplication.quit)

        # --- submenú de voz ---
        s = self.voice.settings
        check(vmenu, "Activar voz", self.voice.on, self._toggle_voice)
        check(vmenu, "Solo con cascos", s["only_headphones"], lambda v: self.voice.set("only_headphones", v))
        vmenu.addSeparator()
        vmenu.addMenu(choices(vmenu, "Elegir voz (se oye al elegir)", [(n, n) for n in VOICES], s["voice"],
                              self._choose_voice))
        el = talk_ui.neon_menu(vmenu, "ElevenLabs (voz más natural)")
        el.addAction("Configurar clave...", self._eleven_setup)
        if s.get("eleven_key"):
            check(el, "Usar ElevenLabs en el chat", bool(s.get("eleven_on")), lambda v: self.voice.set("eleven_on", v))
            voices = {vid: vname for vname, vid in s.get("eleven_voices", [])}
            el.addMenu(choices(el, "Elegir voz", [(vid, vname) for vid, vname in voices.items()],
                               s.get("eleven_voice"), lambda vid: self._eleven_pick(voices[vid], vid)))
            el.addMenu(choices(el, "Calidad", [("flash", "Rápida (gasta la mitad)"), ("natural", "La más natural")],
                               s.get("eleven_model", "flash"), lambda k: self.voice.set("eleven_model", k)))
            el.addAction("Ver saldo del mes", self._eleven_balance)
        vmenu.addMenu(el)
        vmenu.addSeparator()
        vmenu.addAction("Hablarle: mantén Ctrl+Alt+Espacio").setEnabled(False)
        vmenu.addAction("Callarla  (Ctrl+Alt+M)", self.voice.stop)

        menu.exec(event.globalPos())

    def _set_gravity(self, on):
        self.gravity_on = on
        if on and self.surface == "free":
            self._start_fall()


class ModelUpdater(QThread):
    """Si la personalidad o el perfil han cambiado, rehace el modelo nyx sin molestar."""

    def run(self):
        try:
            if persona.ollama_running() and persona.has_model(persona.base_model()) and persona.needs_update():
                persona.create_model()
        except Exception:  # noqa: BLE001 - si falla, se usa el modelo que ya había
            pass


def _log_crash(kind, value, tb):
    """Sin consola no se ven los errores: se apuntan en %APPDATA%\\Nyx\\errores.log."""
    import traceback
    with open(config.DATA_DIR / "errores.log", "a", encoding="utf-8") as f:
        f.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        traceback.print_exception(kind, value, tb, file=f)
    sys.__excepthook__(kind, value, tb)


def _selftest():
    """Nyx.exe --selftest: comprueba que el paquete lleva todo dentro (resultado en autoprueba.txt)."""
    import importlib
    lines = []
    for mod in ["requests", "numpy", "PIL", "PySide6.QtMultimedia", "edge_tts",
                "faster_whisper", "ctranslate2", "sounddevice", "pycaw.pycaw", "comtypes"]:
        try:
            importlib.import_module(mod)
            lines.append(f"OK    {mod}")
        except Exception as e:  # noqa: BLE001
            lines.append(f"FALLO {mod}: {e}")
    lines.append(f"sprites: {len(list(config.SPRITES.glob('*.png')))}  icono: {config.ICON.exists()}  "
                 f"personalidad: {config.PERSONA.exists()}")
    (config.DATA_DIR / "autoprueba.txt").write_text("\n".join(lines), encoding="utf-8")


def main():
    if "--selftest" in sys.argv:
        _selftest()
        return
    sys.excepthook = _log_crash
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(config.ICON)))

    # Primera vez (o falta el modelo): asistente de configuración
    if not config.has_profile() or (persona.ollama_running() and not persona.has_model(persona.base_model())):
        if SetupWizard().exec() != SetupWizard.Accepted:
            return
    updater = ModelUpdater()
    updater.start()

    nyx = Nyx()
    nyx.show()

    hotkeys = [GlobalHotkey("N", nyx.open_chat_from_hotkey, 1),
               GlobalHotkey(" ", nyx.listen, 2),          # mantener pulsado para hablarle
               GlobalHotkey("M", nyx.voice.stop, 3)]      # callarla
    for hk in hotkeys:
        app.installNativeEventFilter(hk)
        app.aboutToQuit.connect(hk.unregister)

    tray = QSystemTrayIcon(QIcon(str(config.ICON)), app)
    tray.setToolTip("Nyx  ·  Ctrl+Alt+N para hablar")
    menu = talk_ui.neon_menu()
    show = QAction("Mostrar / ocultar", menu, triggered=lambda: nyx.setVisible(not nyx.isVisible()))
    menu.addAction(QAction("Mainframe (ajustes)", menu, triggered=nyx.open_mainframe))
    quit_ = QAction("Salir", menu, triggered=app.quit)
    menu.addAction(show)
    menu.addAction(quit_)
    tray.setContextMenu(menu)
    tray.show()
    nyx.tray = tray

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
