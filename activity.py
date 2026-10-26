"""Qué está haciendo el usuario: mira la ventana activa y la clasifica (programar, jugar, ver vídeos...).

Todo se queda en el ordenador: el título de la ventana solo se le pasa al modelo local.
"""
import ctypes
import os
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

CODE = {"code.exe", "idea64.exe", "netbeans64.exe", "netbeans.exe", "pycharm64.exe", "devenv.exe",
        "eclipse.exe", "sublime_text.exe", "notepad++.exe", "rider64.exe", "android studio.exe", "studio64.exe"}
BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "opera_gx.exe"}
OFFICE = {"winword.exe": "Word", "excel.exe": "Excel", "powerpnt.exe": "PowerPoint", "onenote.exe": "OneNote"}
CHAT_APPS = {"discord.exe": "Discord", "whatsapp.exe": "WhatsApp", "telegram.exe": "Telegram"}
MUSIC = {"spotify.exe": "Spotify"}
GAME_EXES = {"leagueclientux.exe": "League of Legends", "league of legends.exe": "League of Legends",
             "valorant-win64-shipping.exe": "Valorant", "riotclientux.exe": "Riot Client",
             "minecraft.exe": "Minecraft", "javaw.exe": None}
GAME_PATHS = ("steamapps\\common", "epic games", "xboxgames", "riot games", "gog galaxy\\games")
IGNORE = {"explorer.exe", "searchhost.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe",
          "lockapp.exe", "applicationframehost.exe", "taskmgr.exe"}

# Palabras en el título del navegador
VIDEO = ("youtube", "netflix", "twitch", "prime video", "disney+", "crunchyroll", "hbo")
STUDY = ("alexia", "moodle", "campus", "stucom", "w3schools", "stack overflow", "stackoverflow", "github",
         "mdn", "documentation", "documentación", "javadoc", "classroom", "teams", "prueba", "examen",
         "ejercicio", "apuntes", "práctica", "practica", "actividad", "tutorial", "curso")
SOCIAL = ("instagram", "tiktok", "twitter", " / x", "reddit", "facebook")
AI = ("chatgpt", "claude", "gemini", "copilot")


def foreground():
    """(exe, ruta, título, pantalla completa) de la ventana que tienes delante, o None."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return None                       # es la propia Nyx
    path = ""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if h:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            path = buf.value
        kernel32.CloseHandle(h)
    n = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, title, n + 1)
    return os.path.basename(path).lower(), path.lower(), title.value, _is_fullscreen(hwnd)


def _is_fullscreen(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.right - r.left) >= user32.GetSystemMetrics(0) and (r.bottom - r.top) >= user32.GetSystemMetrics(1)


def _clean_title(title, cut=(" - Google Chrome", " - Microsoft Edge", " — Mozilla Firefox", " - Brave", " - Opera")):
    for c in cut:
        title = title.replace(c, "")
    title = "".join(ch if ch.isprintable() else "-" for ch in title)
    return title.strip()


def classify(info):
    """Devuelve (categoría, detalle) o None. Categorías: code, game, video, study, social, ai, office, chat, music, web."""
    if not info:
        return None
    exe, path, title, _ = info
    low = title.lower()
    if exe in IGNORE or not title:
        return None
    if exe in CODE:
        return "code", title
    if exe in GAME_EXES:
        return "game", GAME_EXES[exe] or title
    if any(p in path for p in GAME_PATHS):
        return "game", title
    if exe in OFFICE:
        return "office", OFFICE[exe]
    if exe in CHAT_APPS:
        return "chat", CHAT_APPS[exe]
    if exe in MUSIC:
        return "music", title
    if exe in BROWSERS:
        page = _clean_title(title)
        if any(w in low for w in VIDEO):
            return "video", page
        if any(w in low for w in STUDY):
            return "study", page
        if any(w in low for w in SOCIAL):
            return "social", page
        if any(w in low for w in AI):
            return "ai", page
        return "web", page
    return None


def describe(cat, detail):
    """Frase para contárselo al modelo."""
    return {
        "code": f"está programando ({detail})",
        "game": f"está jugando a {detail}",
        "video": f"está viendo vídeos ({detail})",
        "study": f"está mirando cosas de clase ({detail})",
        "social": f"está en redes sociales ({detail})",
        "ai": f"está usando una IA ({detail})",
        "office": f"está con {detail}",
        "chat": f"está hablando por {detail}",
        "music": f"está escuchando música en Spotify ({detail})",
        "web": f"está navegando ({detail})",
    }.get(cat, "")
