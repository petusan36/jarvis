"""Detección de Ollama en el equipo, sin UI: lo que importa acá es si HAY
un binario ``ollama`` utilizable, no si el servicio está corriendo en este
momento (``ollama serve`` se lanza solo o Jarvis lo levanta después, ver
jarvis/conexion_ia.py::_configurar_local). Separado de pantallas/ollama.py
para poder probarlo sin levantar ninguna ventana de Toga."""

from __future__ import annotations

import shutil
from pathlib import Path

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
