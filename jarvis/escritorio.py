"""Instala un lanzador de escritorio nativo (ícono de doble clic) para Jarvis.

Abre `python -m jarvis` en modo completo (voz + HUD) sin ventana de terminal:
la salida se redirige a un archivo de log, porque el usuario interactúa por
voz y por el HUD, no leyendo la consola. Esto sigue teniendo sentido con el
menú de conexión con IA en ventana (ver ``jarvis.__main__._menu_conexion_ia_ventana``):
redirigir stdout/stderr a un log no afecta la conexión con el WindowServer,
así que el proceso puede igual abrir una ventana nativa real y recibir
clicks con normalidad — lo único que no tiene es una terminal para
input()/print(), que es justo por lo que, sin tty, el menú cae a esa
ventana en vez de a la consola.

No incluye: ícono personalizado (arte), firma/notarización de macOS, ni
desinstalador.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

NOMBRE = "Jarvis"


def instalar_app_escritorio(python: Path | None = None, home: Path | None = None) -> Path:
    """Crea el lanzador para este sistema operativo y devuelve su ruta."""
    python = python or Path(sys.executable)
    home = home or Path.home()
    log = home / ".jarvis" / "jarvis.log"

    if sys.platform == "darwin":
        return _instalar_macos(python, log, home)
    if sys.platform == "win32":
        return _instalar_windows(python, log, home)
    return _instalar_linux(python, log, home)


def _instalar_macos(python: Path, log: Path, home: Path) -> Path:
    app = home / "Applications" / f"{NOMBRE}.app"
    carpeta_macos = app / "Contents" / "MacOS"
    carpeta_macos.mkdir(parents=True, exist_ok=True)
    (app / "Contents" / "Info.plist").write_text(_info_plist(), encoding="utf-8")

    lanzador = carpeta_macos / NOMBRE.lower()
    lanzador.write_text(_script_unix(python, log), encoding="utf-8")
    _hacer_ejecutable(lanzador)
    return app


def _info_plist() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>CFBundleName</key>\n"
        f"    <string>{NOMBRE}</string>\n"
        "    <key>CFBundleExecutable</key>\n"
        f"    <string>{NOMBRE.lower()}</string>\n"
        "    <key>CFBundleIdentifier</key>\n"
        "    <string>com.jarvis.asistente</string>\n"
        "    <key>CFBundlePackageType</key>\n"
        "    <string>APPL</string>\n"
        "    <key>CFBundleShortVersionString</key>\n"
        "    <string>1.0</string>\n"
        "</dict>\n"
        "</plist>\n"
    )


def _instalar_windows(python: Path, log: Path, home: Path) -> Path:
    carpeta = home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    carpeta.mkdir(parents=True, exist_ok=True)
    lanzador = carpeta / f"{NOMBRE}.bat"
    lanzador.write_text(_script_windows(python, log), encoding="utf-8")
    return lanzador


def _script_windows(python: Path, log: Path) -> str:
    pythonw = python.with_name("pythonw.exe")
    return (
        "@echo off\r\n"
        f'if not exist "{log.parent}" mkdir "{log.parent}"\r\n'
        f'start "" "{pythonw}" -u -m jarvis >> "{log}" 2>&1\r\n'
    )


def _instalar_linux(python: Path, log: Path, home: Path) -> Path:
    carpeta = home / ".local" / "share" / "applications"
    carpeta.mkdir(parents=True, exist_ok=True)
    entrada = carpeta / "jarvis.desktop"
    entrada.write_text(_entrada_linux(python, log), encoding="utf-8")
    _hacer_ejecutable(entrada)
    return entrada


def _entrada_linux(python: Path, log: Path) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={NOMBRE}\n"
        f'Exec=/bin/sh -c \'mkdir -p "{log.parent}" && exec "{python}" -u -m jarvis >> "{log}" 2>&1\'\n'
        "Terminal=false\n"
        "Categories=Utility;\n"
    )


def _script_unix(python: Path, log: Path) -> str:
    return (
        "#!/bin/bash\n"
        f'mkdir -p "{log.parent}"\n'
        f'exec "{python}" -u -m jarvis >> "{log}" 2>&1\n'
    )


def _hacer_ejecutable(ruta: Path) -> None:
    ruta.chmod(ruta.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
