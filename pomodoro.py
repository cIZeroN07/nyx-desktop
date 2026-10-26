"""Temporizador Pomodoro: 25 minutos de estudio y 5 de descanso (15 cada 4 rondas)."""
from PySide6.QtCore import QObject, QTimer, Signal

import config

WORK_MIN = 25
SHORT_BREAK_MIN = 5
LONG_BREAK_MIN = 15


class Pomodoro(QObject):
    message = Signal(str)   # lo que Nyx dice en el bocadillo
    tick = Signal(str)      # tiempo que queda, para el tooltip

    def __init__(self):
        super().__init__()
        self.timer = QTimer(self, interval=1000, timeout=self._tick)
        self.phase = None        # "work", "break" o None
        self.left = 0
        self.rounds = 0

    @property
    def running(self):
        return self.phase is not None

    def start(self):
        self.rounds = 0
        self._begin("work")
        self.message.emit(f"Vale, {WORK_MIN} minutos de estudio. Nada de móvil, que te estoy vigilando.")

    def stop(self):
        self.timer.stop()
        self.phase = None
        self.tick.emit("")
        self.message.emit(f"Pomodoro parado. Has hecho {self.rounds} rondas, no está mal.")

    def _begin(self, phase):
        self.phase = phase
        if phase == "work":
            self.left = WORK_MIN * 60
        else:
            self.left = (LONG_BREAK_MIN if self.rounds % 4 == 0 else SHORT_BREAK_MIN) * 60
        self.timer.start()
        self._tick(advance=False)

    def _tick(self, advance=True):
        if advance:
            self.left -= 1
        if self.left <= 0:
            if self.phase == "work":
                self.rounds += 1
                self._begin("break")
                long_break = self.rounds % 4 == 0
                mins = LONG_BREAK_MIN if long_break else SHORT_BREAK_MIN
                extra = " Te lo has ganado." if long_break else ""
                self.message.emit(f"¡Descanso, {config.nick()}! {mins} minutos.{extra} Ronda {self.rounds} hecha.")
            else:
                self._begin("work")
                self.message.emit(f"Se acabó el descanso. Vuelta al lío, {config.name()}.")
            return
        m, s = divmod(self.left, 60)
        label = "Estudiando" if self.phase == "work" else "Descanso"
        self.tick.emit(f"{label}: {m:02d}:{s:02d}")
