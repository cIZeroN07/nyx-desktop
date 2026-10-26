"""Rutas y perfil del usuario.

- APP_DIR: donde están el programa y sus imágenes (en el instalado, la carpeta del .exe).
- DATA_DIR: donde se guardan memoria y ajustes (%APPDATA%\\Nyx), que siempre se puede escribir.
- El perfil (nombre, nick, qué hace) se pregunta la primera vez, para que Nyx sirva a cualquiera.
"""
import json
import os
import shutil
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    APP_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    APP_DIR = Path(__file__).resolve().parent

DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "Nyx"
SPRITES = APP_DIR / "assets" / "sprites"
ICON = APP_DIR / "assets" / "nyx.ico"
PERSONA = APP_DIR / "Modelfile"
SKINS_DIR = APP_DIR / "assets" / "skins"


def skin_meta(skin_id):
    """Contenido de skin.json de una apariencia ({} para la original)."""
    meta = SKINS_DIR / skin_id / "skin.json"
    try:
        return json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
    except ValueError:
        return {}


def skins():
    """Apariencias disponibles: {id: (nombre, carpeta, altura del asiento en sit.png)}.
    La original está en assets/sprites; las demás en assets/skins/<id>/ con un skin.json."""
    found = {"nyx": ("Nyx (original)", SPRITES, 0.53)}
    if SKINS_DIR.is_dir():
        for d in sorted(SKINS_DIR.iterdir()):
            meta = d / "skin.json"
            if (d / "idle.png").exists():
                try:
                    info = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
                except ValueError:
                    info = {}
                found[d.name] = (info.get("name", d.name.title()), d, float(info.get("sit_line", 0.52)))
    return found
PROFILE_FILE = DATA_DIR / "profile.json"

DEFAULT_PROFILE = {"name": "", "nick": "", "about": ""}


def _migrate_old_data():
    """La primera versión guardaba la memoria dentro de la carpeta del proyecto: se copia una vez.
    El perfil no se copia: lo pide el asistente de primera vez."""
    old = APP_DIR / "memory"
    if old.is_dir() and not DATA_DIR.exists():
        shutil.copytree(old, DATA_DIR)


def load_profile():
    try:
        data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULT_PROFILE, **data}


def save_profile(profile):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_FILE.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    PROFILE.clear()
    PROFILE.update(profile)


PROFILE = {}
_migrate_old_data()
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROFILE.update(load_profile())


def has_profile():
    return bool(PROFILE.get("name"))


def name():
    return PROFILE.get("name") or "choom"


def nick():
    return PROFILE.get("nick") or name()


def personalize(text):
    """Cambia los nombres de ejemplo de las plantillas por los del usuario."""
    return (text.replace("{NAME}", name()).replace("{NICK}", nick())
            .replace("{ABOUT}", PROFILE.get("about") or "No has contado mucho de ti todavía."))
