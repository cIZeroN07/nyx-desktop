"""Escucha el volumen de Spotify (o de la app de música que suene) para que Nyx baile al ritmo."""
from comtypes import CoInitialize
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

MUSIC_APPS = {"spotify.exe", "music.ui.exe", "applemusic.exe", "tidal.exe", "deezer.exe", "itunes.exe"}


class MusicMeter:
    def __init__(self):
        CoInitialize()
        self.meter = None
        self.app = None

    def refresh(self):
        """Busca una app de música que esté sonando ahora. Devuelve True si hay alguna."""
        self.meter, self.app = None, None
        try:
            for s in AudioUtilities.GetAllSessions():
                proc = s.Process
                if proc and proc.name().lower() in MUSIC_APPS and s.State == 1:     # 1 = sonando
                    self.meter = s._ctl.QueryInterface(IAudioMeterInformation)
                    self.app = proc.name()
                    return True
        except Exception:  # noqa: BLE001 - si el sistema de audio falla, simplemente no baila
            pass
        return False

    def level(self):
        """Volumen instantáneo de 0 a 1."""
        if self.meter is None:
            return 0.0
        try:
            return float(self.meter.GetPeakValue())
        except Exception:  # noqa: BLE001
            self.meter = None
            return 0.0
