"""Voz de Nyx: habla con las voces de Microsoft (edge-tts) y te escucha con Whisper.

- Por defecto está callada; se enciende desde el menú.
- "Solo con cascos": si no hay auriculares conectados, no habla (para clase).
- El micro solo graba mientras mantienes pulsado Ctrl + Alt + Espacio.
"""
import asyncio
import ctypes
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

import config
import memory

SETTINGS = memory.DATA / "settings.json"
# nombre: (voz de Microsoft, velocidad, tono)
VOICES = {
    "Elvira": ("es-ES-ElviraNeural", "+0%", "+0Hz"),       # sin retocar: suena más natural
    "Ximena": ("es-ES-XimenaNeural", "+0%", "+0Hz"),
    "Elvira grave": ("es-ES-ElviraNeural", "+0%", "-18Hz"),
    "Ximena aguda": ("es-ES-XimenaNeural", "+10%", "+12Hz"),
    "Ava (acento extranjero)": ("en-US-AvaMultilingualNeural", "+4%", "+0Hz"),
    "Emma (acento extranjero)": ("en-US-EmmaMultilingualNeural", "+4%", "+0Hz"),
    "Vivienne (francesa)": ("fr-FR-VivienneMultilingualNeural", "+4%", "+0Hz"),
    "Seraphina (alemana)": ("de-DE-SeraphinaMultilingualNeural", "+4%", "+0Hz"),
}
HEADPHONE_WORDS = ("auricular", "headphone", "headset", "cascos", "wh-1000", "buds", "airpods", "manos libres",
                   "hands-free")
FORM_FACTOR_KEY = "{1DA5D803-D492-4EDD-8C23-E0C0FFEE7F0E} 0"   # 3 = auriculares, 5 = headset
SAMPLE_RATE = 16000
VK_SPACE = 0x20


def load_settings():
    s = {"voice_on": False, "only_headphones": True, "voice": "Elvira"}
    s.update(memory._read(SETTINGS, {}))
    return s


def save_settings(s):
    memory._write(SETTINGS, s)


def list_mics():
    """[(nombre, índice)] de los micrófonos (solo los del sistema de audio por defecto, para no repetir)."""
    import sounddevice as sd
    try:
        default_api = sd.query_devices(kind="input")["hostapi"]
        return [(d["name"], i) for i, d in enumerate(sd.query_devices())
                if d["max_input_channels"] > 0 and d["hostapi"] == default_api]
    except Exception:  # noqa: BLE001
        return []


def mic_level(device=None, seconds=1.5):
    """Graba un momento y devuelve el volumen máximo (0-1), para probar el micro."""
    import sounddevice as sd
    data = sd.rec(int(SAMPLE_RATE * seconds), samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=device)
    sd.wait()
    return float(np.abs(data).max())


def headphones_connected():
    """¿La salida de sonido actual son unos cascos?"""
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize()
        dev = AudioUtilities.GetSpeakers()
        name = (getattr(dev, "FriendlyName", "") or "").lower()
        if any(w in name for w in HEADPHONE_WORDS):
            return True
        props = getattr(dev, "properties", {}) or {}
        for key, value in props.items():
            if str(key).upper() == FORM_FACTOR_KEY and value in (3, 5):
                return True
    except Exception:  # noqa: BLE001 - si no podemos saberlo, mejor callada
        pass
    return False


def speakable(text):
    """Quita lo que no se puede leer en voz alta (código, emojis, símbolos)."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"[^\w\s.,;:¡!¿?()'\"-]", " ", text)
    text = re.sub(r"c[Il]ZeroN", "Zerón", text)      # para que pronuncie bien el nick
    return re.sub(r"\s+", " ", text).strip()


class _TTSWorker(QThread):
    ready = Signal(str)

    def __init__(self, text, voice):
        super().__init__()
        self.text, self.voice = text, voice      # voice = (nombre de Microsoft, velocidad, tono)

    def run(self):
        import edge_tts
        out = Path(tempfile.gettempdir()) / f"nyx_voice_{id(self)}.mp3"
        name, rate, pitch = self.voice
        try:
            asyncio.run(edge_tts.Communicate(self.text, name, rate=rate, pitch=pitch).save(str(out)))
            self.ready.emit(str(out))
        except Exception:  # noqa: BLE001 - sin internet, simplemente no habla
            pass


ELEVEN = "https://api.elevenlabs.io/v1"
# Voces de chica que vienen de serie en todas las cuentas (por si la clave no deja listar las voces)
ELEVEN_PREMADE = [("Jessica (joven y alegre)", "cgSgspJ2msm6clMCkdW9"), ("Sarah (suave)", "EXAVITQu4vr4xnSDxMaL"),
                  ("Laura (con carácter)", "FGY2WhTYpPnrIDTdsKH5"), ("Lily (cálida)", "pFZP5JQG7iQjIQuC4Bku"),
                  ("Alice (seria)", "Xb7hH8MSUJpSbSDYk0k2"), ("Matilda (amable)", "XrExE9yKIg1WjnnlVkGX")]
ELEVEN_MODELS = {"flash": "eleven_flash_v2_5", "natural": "eleven_multilingual_v2"}


class ElevenOut(Exception):
    """Se ha acabado el saldo del mes (o la clave no vale)."""


def eleven_tts(text, key, voice_id, model, out):
    import requests
    body = {"text": text, "model_id": ELEVEN_MODELS.get(model, ELEVEN_MODELS["flash"]),
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.3}}
    if model == "flash":
        body["language_code"] = "es"
    r = requests.post(f"{ELEVEN}/text-to-speech/{voice_id}?output_format=mp3_44100_128",
                      headers={"xi-api-key": key}, json=body, timeout=30)
    if r.status_code in (401, 402, 429) or "quota" in r.text[:300].lower():
        raise ElevenOut(r.text[:200])
    r.raise_for_status()
    Path(out).write_bytes(r.content)


def eleven_voices(key):
    """Voces de la cuenta. Si la clave no tiene permiso para listarlas, las de serie (comprobando que habla)."""
    import requests
    r = requests.get(f"{ELEVEN}/voices", headers={"xi-api-key": key}, timeout=15)
    if r.status_code == 401 and "missing_permissions" in r.text:
        test = requests.post(f"{ELEVEN}/text-to-speech/{ELEVEN_PREMADE[0][1]}", headers={"xi-api-key": key},
                             json={"text": "Hola", "model_id": ELEVEN_MODELS["flash"]}, timeout=30)
        test.raise_for_status()
        return list(ELEVEN_PREMADE)
    r.raise_for_status()
    return [(v["name"], v["voice_id"]) for v in r.json().get("voices", [])]


def eleven_left(key):
    """(usados, límite) de este mes."""
    import requests
    r = requests.get(f"{ELEVEN}/user/subscription", headers={"xi-api-key": key}, timeout=15)
    r.raise_for_status()
    d = r.json()
    return d.get("character_count", 0), d.get("character_limit", 0)


class _ElevenWorker(QThread):
    ready = Signal(str)
    out_of_credit = Signal()
    fallback = Signal(str)      # si falla, se lee con la voz de Microsoft

    def __init__(self, text, settings):
        super().__init__()
        self.text, self.s = text, dict(settings)

    def run(self):
        out = Path(tempfile.gettempdir()) / f"nyx_voice_{id(self)}.mp3"
        try:
            eleven_tts(self.text, self.s["eleven_key"], self.s["eleven_voice"], self.s.get("eleven_model", "flash"), out)
            self.ready.emit(str(out))
        except ElevenOut:
            self.out_of_credit.emit()
            self.fallback.emit(self.text)
        except Exception:  # noqa: BLE001 - sin internet, etc.
            self.fallback.emit(self.text)


class _STTWorker(QThread):
    heard = Signal(str)
    _model = None
    _lock = threading.Lock()

    def __init__(self, audio):
        super().__init__()
        self.audio = audio

    def run(self):
        from faster_whisper import WhisperModel
        with self._lock:
            if _STTWorker._model is None:
                # "small" entiende bien el español y va fluido en el procesador
                _STTWorker._model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _ = _STTWorker._model.transcribe(self.audio, language="es", vad_filter=True,
                                                   initial_prompt=f"Nyx, {config.name()}, Night City.")
        text = " ".join(s.text for s in segments).strip()
        self.heard.emit(text)


class Voice(QObject):
    speaking = Signal(bool)
    listening = Signal(bool)
    heard = Signal(str)
    status = Signal(str)       # mensajes cortos para el bocadillo
    level = Signal(float)      # volumen del micro (para las ondas de la pastilla)

    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.output)
        self.player.playbackStateChanged.connect(
            lambda st: self.speaking.emit(st == QMediaPlayer.PlaybackState.PlayingState))
        self.workers = []
        self.stream = None
        self.chunks = []
        self.key_poll = QTimer(self, interval=40, timeout=self._check_release)

    # ---------- ajustes ----------
    def mic(self):
        """Micrófono elegido en el Mainframe (None = el de Windows por defecto)."""
        return self.settings.get("mic")

    @property
    def on(self):
        return self.settings["voice_on"]

    def set(self, key, value):
        self.settings[key] = value
        save_settings(self.settings)

    # ---------- hablar ----------
    def can_speak(self):
        # En conversación por voz habla aunque la voz esté apagada (si la estás hablando, quieres oírla)
        return (self.on or self.conversation) and (not self.settings["only_headphones"] or headphones_connected())

    def eleven_ready(self):
        s = self.settings
        if not (s.get("eleven_on") and s.get("eleven_key") and s.get("eleven_voice")):
            return False
        # Si se acabó el saldo, esperar al mes siguiente
        return s.get("eleven_out_month") != datetime.now().strftime("%Y-%m")

    def speak(self, text, premium=False):
        """premium=True (respuestas del chat) usa ElevenLabs si está configurado."""
        text = speakable(text)
        if not text or not self.can_speak():
            return
        if premium and self.eleven_ready():
            w = _ElevenWorker(text, self.settings)
            w.fallback.connect(self._speak_edge)
            w.out_of_credit.connect(self._eleven_out)
            self._run(w)
        else:
            self._speak_edge(text)

    def _speak_edge(self, text):
        self._run(_TTSWorker(text, VOICES.get(self.settings["voice"], VOICES["Elvira"])))

    def _run(self, w):
        w.ready.connect(self._play)
        w.finished.connect(lambda: self.workers.remove(w))
        self.workers.append(w)
        w.start()

    def _eleven_out(self):
        self.set("eleven_out_month", datetime.now().strftime("%Y-%m"))
        self.status.emit("Se me ha acabado la voz buena este mes. Uso la normal hasta el mes que viene.")

    def _play(self, path):
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def stop(self):
        self.player.stop()

    def preview(self, text, premium=False):
        """Probar una voz aunque esté apagada o sin cascos (lo pide el usuario a propósito)."""
        text = speakable(text)
        if premium and self.eleven_ready():
            w = _ElevenWorker(text, self.settings)
            w.fallback.connect(self._speak_edge)
            w.out_of_credit.connect(self._eleven_out)
            self._run(w)
        else:
            self._speak_edge(text)

    # ---------- escuchar (walkie-talkie) ----------
    def start_listening(self):
        if self.stream is not None or self.conversation:
            return
        import sounddevice as sd
        self.stop()
        self.chunks = []
        try:
            self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=self.mic(),
                                         callback=lambda data, *_: self.chunks.append(data.copy()))
            self.stream.start()
        except Exception:  # noqa: BLE001
            self.stream = None
            self.status.emit("No encuentro el micrófono.")
            return
        self.listening.emit(True)
        self.key_poll.start()

    def _check_release(self):
        if not ctypes.windll.user32.GetAsyncKeyState(VK_SPACE) & 0x8000:
            self.stop_listening()

    def stop_listening(self):
        self.key_poll.stop()
        if self.stream is None:
            return
        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.listening.emit(False)
        if not self.chunks:
            return
        audio = np.concatenate(self.chunks)[:, 0]
        if len(audio) < SAMPLE_RATE * 0.4:      # menos de medio segundo: ha sido sin querer
            return
        self.status.emit("Procesando...")
        w = _STTWorker(audio)
        w.heard.connect(self._heard)
        w.finished.connect(lambda: self.workers.remove(w))
        self.workers.append(w)
        w.start()

    def _heard(self, text):
        self.stt_busy = False
        if text:
            self.heard.emit(text)
        elif not self.conversation:
            self.status.emit("No te he oído bien. Mantén pulsado Ctrl + Alt + Espacio mientras hablas.")

    # ---------- conversación por voz (botón de las ondas) ----------
    conversation = False
    stt_busy = False
    muted = False
    busy_check = None          # función que dice si Nyx está pensando (entonces no escucha)

    def start_conversation(self):
        if self.conversation or self.stream is not None:
            return
        import sounddevice as sd
        self.conv_chunks, self.rms, self.noise = [], 0.0, 0.01
        self.in_speech, self.last_voice, self.muted = False, 0.0, False
        self.conv_lock = threading.Lock()

        def callback(data, *_):
            self.rms = float(np.sqrt(np.mean(data ** 2)))
            with self.conv_lock:
                self.conv_chunks.append(data[:, 0].copy())

        try:
            self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=self.mic(),
                                         blocksize=800, callback=callback)
            self.stream.start()
        except Exception:  # noqa: BLE001
            self.stream = None
            self.status.emit("No encuentro el micrófono.")
            return
        self.conversation = True
        self.conv_timer = QTimer(self, interval=50, timeout=self._conv_tick)
        self.conv_timer.start()
        self.listening.emit(True)

    def stop_conversation(self):
        if not self.conversation:
            return
        self.conversation = False
        self.conv_timer.stop()
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.level.emit(0.0)
        self.listening.emit(False)

    def toggle_mute(self):
        self.muted = not self.muted
        return self.muted

    def _conv_tick(self):
        lvl = self.rms
        self.level.emit(0.0 if self.muted else min(1.0, lvl * 12))
        speaking = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        thinking = self.busy_check() if self.busy_check else False
        if self.muted or speaking or thinking or self.stt_busy:
            with self.conv_lock:
                self.conv_chunks = []
            self.in_speech = False
            return
        now = time.monotonic()
        threshold = max(0.02, self.noise * 3)
        if lvl > threshold:
            self.in_speech = True
            self.last_voice = now
        elif not self.in_speech:
            self.noise = self.noise * 0.95 + lvl * 0.05            # ruido de fondo de la habitación
            with self.conv_lock:
                self.conv_chunks = self.conv_chunks[-12:]           # guardar solo el último medio segundo
        if self.in_speech and now - self.last_voice > 1.0:          # 1 s de silencio: ha terminado la frase
            with self.conv_lock:
                audio = np.concatenate(self.conv_chunks) if self.conv_chunks else np.zeros(0, np.float32)
                self.conv_chunks = []
            self.in_speech = False
            if len(audio) > SAMPLE_RATE * 0.6:
                self.stt_busy = True
                w = _STTWorker(audio)
                w.heard.connect(self._heard)
                w.finished.connect(lambda: self.workers.remove(w))
                self.workers.append(w)
                w.start()
