"""Instala un lanzador de escritorio nativo (ícono de doble clic) para Jarvis.

Copia el bundle standalone ya construido con PyInstaller (ver
``scripts/build_app.sh`` y ``jarvis.spec``) a la ubicación de escritorio de
cada sistema. El resultado NO depende del repo ni del venv de desarrollo
para arrancar: es una copia completa e independiente.

- macOS: copia ``dist/Jarvis.app`` a ``~/Applications/Jarvis.app``.
- Windows: copia la carpeta ``dist/jarvis`` (con ``jarvis.exe`` adentro) a
  ``%LOCALAPPDATA%\\Jarvis\\app`` y crea un acceso directo (``.bat``) en el
  menú de inicio que lanza ese ``.exe`` directamente (ya es standalone, no
  hace falta invocar ningún Python).
- Linux: copia la carpeta ``dist/jarvis`` a ``~/.local/share/jarvis/app`` y
  crea una entrada ``.desktop`` que apunta al binario ``jarvis`` de esa
  carpeta.

Si el bundle todavía no se construyó (no existe ``dist/Jarvis.app`` ni
``dist/jarvis`` junto al repo), se lanza ``RuntimeError`` con instrucciones
claras para correr primero ``scripts/build_app.sh``.

El doble clic arranca sin terminal, así que el menú de conexión con IA cae
a la ventana nativa (ver ``jarvis.conexion_ia._menu_conexion_ia_ventana``) en
vez de a ``input()``/``print()`` — eso no depende de cómo se instaló, solo
de si hay una tty real o no.

No incluye: ícono personalizado (arte), firma/notarización de macOS, ni
desinstalador. Sin sesión ni clave configuradas todavía, la primera vez hay
que correr el bundle (o ``python -m jarvis``) desde una terminal (ver README).
"""

from __future__ import annotations

import shutil
import stat
import sys
from pathlib import Path

NOMBRE = "Jarvis"

RAIZ_REPO_POR_DEFECTO = Path(__file__).resolve().parent.parent

MENSAJE_FALTA_BUILD = (
    "No encuentro el bundle standalone de Jarvis ({origen}). "
    "Construilo primero con: scripts/build_app.sh "
    "(requiere pip install -e \".[build]\")."
)


def instalar_app_escritorio(home: Path | None = None, repo_raiz: Path | None = None) -> Path:
    """Copia el bundle ya construido al lugar de escritorio de este sistema
    y devuelve su ruta. Lanza RuntimeError si el bundle no se construyó
    todavía (ver ``scripts/build_app.sh``)."""
    home = home or Path.home()
    repo_raiz = repo_raiz or RAIZ_REPO_POR_DEFECTO

    if sys.platform == "darwin":
        return _instalar_macos(repo_raiz, home)
    if sys.platform == "win32":
        return _instalar_windows(repo_raiz, home)
    return _instalar_linux(repo_raiz, home)


def _instalar_macos(repo_raiz: Path, home: Path) -> Path:
    origen = repo_raiz / "dist" / "Jarvis.app"
    _validar_origen(origen)

    destino = home / "Applications" / "Jarvis.app"
    _copiar_bundle(origen, destino)
    return destino


def _instalar_windows(repo_raiz: Path, home: Path) -> Path:
    origen = repo_raiz / "dist" / "jarvis"
    _validar_origen(origen)

    carpeta_app = home / "AppData" / "Local" / "Jarvis" / "app"
    _copiar_bundle(origen, carpeta_app)

    carpeta_menu = home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    carpeta_menu.mkdir(parents=True, exist_ok=True)
    lanzador = carpeta_menu / f"{NOMBRE}.bat"
    lanzador.write_text(_script_windows_standalone(carpeta_app / "jarvis.exe"), encoding="utf-8")
    return lanzador


def _script_windows_standalone(ejecutable: Path) -> str:
    # El .exe generado por PyInstaller ya es standalone (no necesita ningún
    # Python instalado) y se construyó con console=False: "start" alcanza
    # para abrirlo sin ventana de consola.
    return f'@echo off\r\nstart "" "{ejecutable}"\r\n'


def _instalar_linux(repo_raiz: Path, home: Path) -> Path:
    origen = repo_raiz / "dist" / "jarvis"
    _validar_origen(origen)

    carpeta_app = home / ".local" / "share" / "jarvis" / "app"
    _copiar_bundle(origen, carpeta_app)

    carpeta_menu = home / ".local" / "share" / "applications"
    carpeta_menu.mkdir(parents=True, exist_ok=True)
    entrada = carpeta_menu / "jarvis.desktop"
    entrada.write_text(_entrada_linux(carpeta_app / "jarvis"), encoding="utf-8")
    _hacer_ejecutable(entrada)
    return entrada


def _entrada_linux(ejecutable: Path) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={NOMBRE}\n"
        f"Exec={ejecutable}\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
    )


def _validar_origen(origen: Path) -> None:
    if not origen.is_dir():
        raise RuntimeError(MENSAJE_FALTA_BUILD.format(origen=origen))


def _copiar_bundle(origen: Path, destino: Path) -> Path:
    """Copia completa (no symlink): el resultado tiene que seguir funcionando
    aunque el repo (y el bundle original en dist/) se borren o se muevan."""
    if destino.exists():
        shutil.rmtree(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(origen, destino, symlinks=True)
    return destino


def _hacer_ejecutable(ruta: Path) -> None:
    ruta.chmod(ruta.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
