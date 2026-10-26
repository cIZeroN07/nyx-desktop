"""Lee la plantilla de personalidad (Modelfile) y crea el modelo "nyx" en Ollama para este usuario."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import requests

import config

OLLAMA = "http://127.0.0.1:11434"
DEFAULT_BASE = "gemma4:e4b"
MODEL = "nyx"


def base_model():
    """El "cerebro" elegido en el Mainframe (por defecto Gemma 4 E4B, de Google)."""
    try:
        s = json.loads((config.DATA_DIR / "settings.json").read_text(encoding="utf-8"))
        return s.get("base_model") or DEFAULT_BASE
    except (OSError, ValueError):
        return DEFAULT_BASE


BASE_MODEL = DEFAULT_BASE      # compatibilidad: usar base_model() para el valor actual


def _template():
    return config.PERSONA.read_text(encoding="utf-8")


def system_text():
    m = re.search(r'SYSTEM\s+"""(.*?)"""', _template(), re.DOTALL)
    return config.personalize(m.group(1).strip()) if m else ""


def examples():
    out = []
    for line in _template().splitlines():
        m = re.match(r"MESSAGE\s+(user|assistant)\s+(.*)", line)
        if m:
            out.append({"role": m.group(1), "content": config.personalize(m.group(2))})
    return out


def parameters():
    params = {}
    for name, value in re.findall(r"^PARAMETER\s+(\w+)\s+(\S+)", _template(), re.MULTILINE):
        params[name] = float(value) if "." in value else int(value)
    return params


HASH_FILE = config.DATA_DIR / "model_version.txt"


def _fingerprint():
    data = json.dumps([base_model(), system_text(), examples(), parameters()], ensure_ascii=False)
    return hashlib.sha1(data.encode("utf-8")).hexdigest()


def create_model():
    """Crea (o actualiza) el modelo "nyx" con el nombre del usuario metido en la personalidad."""
    r = requests.post(f"{OLLAMA}/api/create", timeout=600, json={
        "model": MODEL, "from": base_model(), "system": system_text(),
        "messages": examples(), "parameters": parameters(), "stream": False})
    r.raise_for_status()
    HASH_FILE.write_text(_fingerprint(), encoding="utf-8")


# ---------- comprobaciones de Ollama ----------
def ollama_running():
    try:
        return requests.get(f"{OLLAMA}/api/version", timeout=2).ok
    except requests.RequestException:
        return False


def start_ollama():
    """Intenta abrir Ollama si está instalado pero cerrado. Devuelve False si no está instalado."""
    exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama app.exe"
    if not exe.exists():
        return False
    subprocess.Popen([str(exe)], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return True


def installed_models():
    try:
        return {m["name"] for m in requests.get(f"{OLLAMA}/api/tags", timeout=5).json().get("models", [])}
    except (requests.RequestException, ValueError):
        return set()


def has_model(name):
    models = installed_models()
    return name in models or f"{name}:latest" in models


def needs_update():
    """¿Hay que (re)crear el modelo nyx? (no existe, o la personalidad o el perfil han cambiado)"""
    try:
        old = HASH_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        old = ""
    return old != _fingerprint() or not has_model(MODEL)


def pull_base(progress):
    """Descarga el modelo base llamando a progress(hecho, total, texto)."""
    with requests.post(f"{OLLAMA}/api/pull", json={"model": base_model(), "stream": True},
                       stream=True, timeout=None) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            if data.get("error"):
                raise RuntimeError(data["error"])
            progress(data.get("completed", 0), data.get("total", 0), data.get("status", ""))
