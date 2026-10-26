# Empaquetado de Nyx con PyInstaller.
# Construir:  .venv\Scripts\pyinstaller.exe nyx.spec --noconfirm
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

sprites = [(str(p), "assets/sprites") for p in Path("assets/sprites").glob("*.png") if not p.stem.endswith("_src")]

# NYX_PUBLIC=1: versión para publicar (GitHub Releases), sin la apariencia de Capri
public = os.environ.get("NYX_PUBLIC") == "1"
skins = [(str(p), str(p.parent).replace("\\", "/")) for p in Path("assets/skins").rglob("*")
         if p.is_file() and p.suffix in (".png", ".json", ".md", ".txt")
         and not (public and "capri" in p.parts)]
fonts = [(str(p), "assets/fonts") for p in Path("assets/fonts").glob("*")]

datas = sprites + skins + fonts + [
    ("NOTICE.txt", "."),
    ("assets/nyx.ico", "assets"),
    ("Modelfile", "."),
]
datas += collect_data_files("faster_whisper")        # el detector de voz (silero) va aquí
binaries = collect_dynamic_libs("ctranslate2")

a = Analysis(
    ["nyx.py"],
    datas=datas,
    binaries=binaries,
    hiddenimports=["comtypes.stream", "pycaw.pycaw"],
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Nyx",
    icon="assets/nyx.ico",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Nyx")
