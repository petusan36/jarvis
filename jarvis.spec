# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para empaquetar Jarvis como app standalone.

Este mismo .spec se usa para los tres sistemas (macOS, Windows, Linux) vía
el workflow de CI (.github/workflows/build-app.yml), uno por runner: PyInstaller
no cruza plataformas, un build hecho en Mac solo corre en Mac. En macOS el
resultado es dist/Jarvis.app; en Windows y Linux, dist/jarvis/ (carpeta
onedir con jarvis.exe o el binario jarvis adentro, sin envoltorio .app).

Generado/mantenido a mano (no con `pyi-makespec`) porque el proyecto mezcla
varias dependencias pesadas con detección automática poco confiable:
torch, faster-whisper, kokoro/misaki (TTS), graphiti-core + ladybug (memoria,
con un binario nativo compilado) y PyObjC (ventana nativa de macOS).

Modo elegido: --onedir (carpeta Contents/MacOS/jarvis + Contents/Frameworks,
no un único binario). Un --onefile descomprime todo a un directorio temporal
en cada arranque, lo que es especialmente lento con un bundle de este tamaño
(cientos de MB de torch/transformers) y mucho más difícil de depurar si un
import falla a mitad de arranque: con --onedir se puede inspeccionar
Contents/Frameworks directamente y correr el binario desde terminal para ver
el traceback completo. Para una app con modelos de ML y una ventana nativa,
la facilidad de diagnóstico pesa más que tener un solo archivo.

Los modelos de Whisper y Kokoro NO se incluyen en el bundle: se siguen
descargando a ~/.jarvis o a la caché de huggingface en el primer uso real,
igual que hoy corriendo desde el repo. Ver README para el detalle.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# El paquete jarvis está instalado en modo editable (`pip install -e .`),
# que usa un finder propio (PEP 660) en vez de vivir físicamente en
# site-packages. El analizador estático de PyInstaller (modulegraph) no
# ejecuta ese finder, así que sin esta ruta explícita no encuentra el
# paquete real y lo deja fuera del bundle (ModuleNotFoundError en runtime,
# ya fuera del repo, confirmado empíricamente). Apuntar pathex a la raíz
# del repo resuelve esto sin depender de cómo esté instalado jarvis en el
# venv de build; el resultado final del bundle no referencia esta ruta
# (el código de jarvis queda copiado dentro del .app, no enlazado).
# SPECPATH es una variable que PyInstaller inyecta en el namespace del
# .spec al ejecutarlo (no existe __file__: el .spec se ejecuta con exec()).
RAIZ_REPO = str(Path(SPECPATH).resolve())  # noqa: F821

# --- Dependencias pesadas que necesitan recolección completa -------------
# collect_all trae módulos + datos + binarios de cada paquete. Es la forma
# más confiable de no perder submódulos que PyInstaller no detecta por
# análisis estático puro (torch, transformers y similares cargan plugins
# dinámicamente según el backend disponible).
PAQUETES_COLLECT_ALL = [
    "torch",
    "faster_whisper",
    "kokoro",
    "misaki",
    "piper",
    "graphiti_core",
    "ladybug",  # incluye el binario nativo _lbug.cpython-*.so (ex-Kuzu)
    "neo4j",
    "huggingface_hub",
    "transformers",
    "onnxruntime",
    "sounddevice",
    "soundfile",
    "curated_transformers",
    "spacy_curated_transformers",
]

datas = []
binaries = []
hiddenimports = []

for paquete in PAQUETES_COLLECT_ALL:
    try:
        d, b, h = collect_all(paquete)
    except Exception as error:  # paquete opcional no instalado: seguir sin él
        print(f"[jarvis.spec] aviso: no pude recolectar {paquete!r}: {error}")
        continue
    datas += d
    binaries += b
    hiddenimports += h

# --- PyObjC: solo los frameworks que usa jarvis.hud.ventana_macos ---------
# PyObjC es una dependencia solo-macOS en pyproject.toml (sys_platform ==
# "darwin"): en Windows/Linux ni está instalado, así que no tiene sentido
# pedirle a PyInstaller que lo busque (y en esos dos SO, jarvis.hud ya cae
# solo al modo navegador vía `_abrir_ventana_app`, sin tocar este código).
# El entorno de desarrollo mac tiene instalado el metapaquete pyobjc
# completo (todos los frameworks), pero jarvis solo usa estos tres. Listar
# solo los necesarios evita arrastrar ~150 frameworks que no se usan.
if sys.platform == "darwin":
    hiddenimports += [
        "objc",
        "AppKit",
        "WebKit",
        "Foundation",
        "PyObjCTools",
    ]

# --- Submódulos con import perezoso que PyInstaller podría no ver ---------
hiddenimports += collect_submodules("jarvis")
hiddenimports += ["pyttsx3.drivers"]
if sys.platform == "darwin":
    hiddenimports += ["pyttsx3.drivers.nsss"]
elif sys.platform == "win32":
    hiddenimports += ["pyttsx3.drivers.sapi5"]
else:
    hiddenimports += ["pyttsx3.drivers.espeak"]

# --- Datos propios de jarvis: la página del HUD (hud.html) ----------------
datas += [("jarvis/hud/hud.html", "jarvis/hud")]

a = Analysis(
    ["scripts/jarvis_entry.py"],
    pathex=[RAIZ_REPO],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=["scripts/pyinstaller_hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="jarvis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # app de ventana/voz, no de terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="jarvis",
)

# BUNDLE (el .app de macOS) solo tiene sentido en Darwin. En Windows y Linux
# el resultado útil es directamente la carpeta onedir de COLLECT
# (dist/jarvis/, con jarvis.exe o el binario jarvis adentro): ya es
# standalone, no necesita envoltorio adicional — jarvis.escritorio la copia
# tal cual al instalar el acceso de escritorio en esos dos sistemas.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Jarvis.app",
        icon=None,
        bundle_identifier="com.jarvis.asistente",
        info_plist={
            "CFBundleName": "Jarvis",
            "CFBundleDisplayName": "Jarvis",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSUIElement": False,
            "NSMicrophoneUsageDescription": "Jarvis necesita el micrófono para escucharte.",
        },
    )
