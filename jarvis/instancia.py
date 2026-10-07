"""Instancia única de Jarvis (.pid) y redirección del log cuando corre
como bundle standalone (PyInstaller, ver --instalar-app).

Separado de __main__.py: ver auditoría de arquitectura hexagonal.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _redirigir_log_si_es_bundle_standalone(carpeta_datos: Path) -> None:
    """El bundle standalone (PyInstaller, ver --instalar-app) se abre vía
    LaunchServices (doble clic/`open`), sin terminal ni redirección propia
    como tenía el lanzador fino viejo (que hacía `>> jarvis.log 2>&1` en el
    script de escritorio) — sin esto, cualquier error quedaba invisible, sin
    rastro en ningún lado, justo el bug reportado como "Jarvis abre un
    momento y se cierra" sin poder diagnosticarlo.

    ``sys.frozen`` solo es ``True`` dentro del bundle de PyInstaller — nunca
    en desarrollo ni en los tests, así que esto no afecta `capsys` ni ningún
    comportamiento existente fuera del bundle real."""
    if not getattr(sys, "frozen", False):
        return
    carpeta_datos.mkdir(parents=True, exist_ok=True)
    archivo_log = open(carpeta_datos / "jarvis.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = archivo_log
    sys.stderr = archivo_log


def _tomar_instancia_unica(carpeta_datos: Path) -> bool:
    """Evita abrir dos Jarvis a la vez (ej. doble clic repetido en el ícono).

    Devuelve False si ya hay una instancia viva. Un .pid de un proceso muerto
    (cierre sucio, apagón) se ignora solo: no hace falta borrarlo a mano.
    """
    ruta = carpeta_datos / "jarvis.pid"
    if ruta.is_file():
        try:
            pid_anterior = int(ruta.read_text().strip())
            os.kill(pid_anterior, 0)
            return False  # el proceso sigue vivo
        except ProcessLookupError:
            pass  # el proceso ya no existe: .pid viejo de un cierre sucio
        except (ValueError, OSError):
            pass  # .pid corrupto, o el SO no deja preguntar (ej. permisos, Windows): seguimos
    carpeta_datos.mkdir(parents=True, exist_ok=True)
    ruta.write_text(str(os.getpid()))
    return True


def _liberar_instancia(carpeta_datos: Path) -> None:
    ruta = carpeta_datos / "jarvis.pid"
    try:
        if int(ruta.read_text().strip()) == os.getpid():
            ruta.unlink()
    except (OSError, ValueError):
        pass  # ya no está, o es de otra instancia: no tocar
