"""Descarga el bundle real de Jarvis (publicado por
.github/workflows/release.yml) y lo instala en el lugar de escritorio de
este sistema — sin UI, pensado para correr en un hilo aparte (ver
pantallas/instalacion.py).

Por qué no se reusa ``jarvis.escritorio`` tal cual: ese módulo asume que el
bundle ya está construido al lado de un clon del repo
(``repo_raiz/dist/Jarvis.app``) — sirve para el developer que corrió
``scripts/build_app.sh``, no para un usuario final que solo tiene este
instalador gráfico. ``instalador/`` es además un proyecto Python
independiente (no depende del paquete ``jarvis``, que arrastraría
torch/whisper/etc. — pesado e innecesario antes de que Jarvis mismo
arranque), así que la lógica de "dónde va cada cosa por sistema operativo"
se reimplementa acá (es chica y solo usa la librería estándar), con el
mismo resultado final que ``jarvis.escritorio.instalar_app_escritorio``."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

URL_RELEASES_LATEST = "https://api.github.com/repos/petusan36/jarvis/releases/latest"
NOMBRE = "Jarvis"

_ZIP_POR_PLATAFORMA = {
    "darwin": "jarvis-macos.zip",
    "win32": "jarvis-windows.zip",
    "linux": "jarvis-linux.zip",
}


class ErrorInstalacionJarvis(RuntimeError):
    """No se pudo descargar o instalar el bundle real de Jarvis."""


def _zip_para_esta_plataforma() -> str:
    for prefijo, nombre_zip in _ZIP_POR_PLATAFORMA.items():
        if sys.platform == prefijo or sys.platform.startswith(prefijo):
            return nombre_zip
    raise ErrorInstalacionJarvis(f"Sistema operativo no soportado: {sys.platform}")


def obtener_url_bundle() -> str:
    """URL de descarga directa del zip del bundle para este SO, del último
    release publicado. Lanza ``ErrorInstalacionJarvis`` si no hay releases
    todavía o no incluye el asset de este sistema operativo."""
    nombre_zip = _zip_para_esta_plataforma()
    try:
        with urllib.request.urlopen(URL_RELEASES_LATEST, timeout=15) as respuesta:
            datos = json.loads(respuesta.read())
    except (urllib.error.URLError, TimeoutError) as error:
        raise ErrorInstalacionJarvis(f"No se pudo consultar los releases de Jarvis: {error}") from error
    except json.JSONDecodeError as error:
        raise ErrorInstalacionJarvis("GitHub devolvió algo que no es JSON válido.") from error

    for asset in datos.get("assets", []):
        if asset.get("name") == nombre_zip:
            return asset["browser_download_url"]

    raise ErrorInstalacionJarvis(
        f"El último release de Jarvis no tiene un bundle para este sistema operativo ({nombre_zip})."
    )


def descargar_e_instalar(reportar: Callable[[str], None], home: Path | None = None) -> Path:
    """Descarga el zip del release, lo extrae, e instala el bundle en el
    lugar de escritorio de este sistema. Devuelve la ruta instalada (el
    .app en macOS, el .bat/.desktop en Windows/Linux — mismo contrato que
    ``jarvis.escritorio.instalar_app_escritorio``)."""
    home = home or Path.home()
    url = obtener_url_bundle()

    with tempfile.TemporaryDirectory() as carpeta_temp_str:
        carpeta_temp = Path(carpeta_temp_str)
        ruta_zip = carpeta_temp / "jarvis.zip"

        reportar("Descargando Jarvis...")
        try:
            urllib.request.urlretrieve(url, ruta_zip)
        except (urllib.error.URLError, OSError) as error:
            raise ErrorInstalacionJarvis(f"La descarga falló: {error}") from error

        reportar("Extrayendo...")
        carpeta_extraida = carpeta_temp / "extraido"
        with zipfile.ZipFile(ruta_zip) as zip_abierto:
            zip_abierto.extractall(carpeta_extraida)

        reportar("Instalando...")
        origen = _encontrar_bundle(carpeta_extraida)
        if sys.platform == "darwin":
            resultado = _instalar_macos(origen, home)
        elif sys.platform == "win32":
            resultado = _instalar_windows(origen, home)
        else:
            resultado = _instalar_linux(origen, home)

    reportar("Listo.")
    return resultado


def _encontrar_bundle(carpeta_extraida: Path) -> Path:
    """El zip tiene un solo directorio de primer nivel adentro (Jarvis.app
    en macOS, o la carpeta jarvis/ en Windows/Linux) — eso es lo que hay
    que copiar, no la carpeta temporal que lo contiene."""
    hijos = list(carpeta_extraida.iterdir())
    if len(hijos) != 1:
        raise ErrorInstalacionJarvis(
            f"El bundle descargado no tiene la forma esperada ({len(hijos)} elementos en la raíz, se esperaba 1)."
        )
    return hijos[0]


def _instalar_macos(origen: Path, home: Path) -> Path:
    destino = home / "Applications" / "Jarvis.app"
    return _copiar_bundle(origen, destino)


def _instalar_windows(origen: Path, home: Path) -> Path:
    carpeta_app = home / "AppData" / "Local" / "Jarvis" / "app"
    _copiar_bundle(origen, carpeta_app)

    carpeta_menu = home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    carpeta_menu.mkdir(parents=True, exist_ok=True)
    lanzador = carpeta_menu / f"{NOMBRE}.bat"
    lanzador.write_text(_script_windows(carpeta_app / "jarvis.exe"), encoding="utf-8")
    return lanzador


def _script_windows(ejecutable: Path) -> str:
    return f'@echo off\r\nstart "" "{ejecutable}"\r\n'


def _instalar_linux(origen: Path, home: Path) -> Path:
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


def _copiar_bundle(origen: Path, destino: Path) -> Path:
    if destino.exists():
        shutil.rmtree(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(origen, destino, symlinks=True)
    return destino


def _hacer_ejecutable(ruta: Path) -> None:
    ruta.chmod(ruta.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def abrir_jarvis(resultado: Path) -> None:
    """Lanza el Jarvis recién instalado, a partir de lo que devolvió
    ``descargar_e_instalar`` (el .app en macOS, el .bat en Windows, el
    .desktop en Linux). Falla silenciosa a propósito (ver cada rama):
    si no se pudo abrir solo, el usuario igual tiene el ícono/acceso
    directo ya instalado para abrirlo a mano — no vale la pena romper el
    último paso del wizard por esto."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(resultado)])
        elif sys.platform == "win32":
            os.startfile(str(resultado))  # noqa: no shell=True, sin riesgo de inyección
        else:
            # Linux: lanzar un .desktop directo no es portable entre
            # entornos de escritorio. `gio launch` (parte de glib2/GIO) es
            # el mecanismo moderno más extendido (GNOME y derivados) — no
            # verificado en vivo (sin máquina Linux disponible en esta
            # sesión). Si no está disponible, falla silencioso, igual que
            # las otras dos ramas.
            subprocess.Popen(["gio", "launch", str(resultado)])
    except OSError:
        pass
