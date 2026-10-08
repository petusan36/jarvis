"""Detección e instalación de Ollama en el equipo, sin UI — separado de
pantallas/ollama.py para poder probarlo sin levantar ninguna ventana de
Toga.

Mecanismo de instalación verificado contra la fuente real, no inferido:

- macOS y Linux: ``curl -fsSL https://ollama.com/install.sh | sh`` — bajado
  y leído a mano (no un resumen de terceros) el 2026-10-08. En macOS hace
  un install SILENCIOSO real: descarga ``Ollama-darwin.zip``, lo mueve a
  ``/Applications``, symlinkea el CLI a ``/usr/local/bin/ollama`` y arranca
  la app en segundo plano (``open -a Ollama --args hidden``) — nada de
  interacción humana, mismo script para ambos sistemas operativos (el
  propio comentario del script lo dice: "This script installs Ollama on
  Linux and macOS"). En Linux hace lo equivalente con el paquete nativo de
  esa distro.
- Windows: NO se implementa instalación automática. Investigado: el único
  instalador oficial es ``OllamaSetup.exe`` (sin .msi), y el flag
  silencioso que aparece dando vueltas (``/VERYSILENT`` de Inno Setup) solo
  está confirmado por un agregador de terceros, nunca por Ollama ni en su
  repo — no se va a ejecutar un instalador real de sistema con un flag sin
  confirmar contra la fuente oficial. En Windows, el botón descarga el
  instalador y lo abre para que el usuario termine el asistente nativo.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable

URL_INSTALL_SH = "https://ollama.com/install.sh"
URL_SETUP_WINDOWS = "https://ollama.com/download/OllamaSetup.exe"


class ErrorInstalacionOllama(RuntimeError):
    """La instalación de Ollama falló o no es automática en este SO."""


# Ubicaciones típicas de instalación cuando el binario no quedó en PATH
# (instalador .pkg/.exe no siempre lo agrega a la sesión actual de shell).
_RUTAS_CONOCIDAS = [
    Path("/usr/local/bin/ollama"),
    Path("/opt/homebrew/bin/ollama"),
    Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
    Path("/usr/bin/ollama"),
]


def ollama_instalado() -> bool:
    """¿Hay un binario ``ollama`` utilizable? Primero PATH (cubre el caso
    normal), después las rutas típicas de instalación por si el PATH de
    este proceso no se actualizó todavía (instalador recién corrido)."""
    if shutil.which("ollama") is not None:
        return True
    return any(ruta.is_file() for ruta in _RUTAS_CONOCIDAS)


def instalar_automatico_disponible() -> bool:
    """¿Este sistema operativo tiene un camino de instalación automática
    verificado? Solo macOS y Linux (ver docstring del módulo) — en Windows
    no hay flag silencioso confirmado contra fuente oficial."""
    return sys.platform in ("darwin", "linux")


def instalar_ollama(reportar: Callable[[str], None]) -> None:
    """Instala Ollama de verdad en macOS/Linux corriendo el script oficial
    (bajado en el momento, no embebido — así nunca queda desactualizado ni
    depende de que este instalador se haya construido con una copia vieja).
    Bloqueante: pensado para correr en un hilo aparte (ver
    pantallas/ollama.py), nunca en el hilo de la UI de Toga.

    ``reportar``: callback de una sola línea de texto, llamado con cada
    línea que el script de instalación va imprimiendo — para que la UI
    pueda mostrar progreso real en vez de un spinner ciego.

    En Windows levanta ``ErrorInstalacionOllama`` siempre: no hay
    instalación automática ahí (ver ``instalar_automatico_disponible``)."""
    if not instalar_automatico_disponible():
        raise ErrorInstalacionOllama(
            "La instalación automática no está disponible en Windows todavía "
            "(sin flag silencioso oficial confirmado). Descargá el instalador "
            f"manualmente desde {URL_SETUP_WINDOWS} y corré el asistente."
        )

    reportar("Descargando el script de instalación oficial de Ollama...")
    try:
        proceso = subprocess.Popen(
            ["sh", "-c", f"curl -fsSL {URL_INSTALL_SH} | sh"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as error:
        raise ErrorInstalacionOllama(f"No se pudo iniciar la instalación: {error}") from error

    assert proceso.stdout is not None
    for linea in proceso.stdout:
        linea = linea.rstrip()
        if linea:
            reportar(linea)

    codigo = proceso.wait()
    if codigo != 0:
        raise ErrorInstalacionOllama(f"El instalador de Ollama terminó con error (código {codigo}).")
