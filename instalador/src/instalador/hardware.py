"""Escaneo de hardware, sin UI: lo que necesita la pantalla de selección de
modelo (siguiente incremento) para recomendar un tamaño de modelo acorde a
la máquina — no hace falta precisión de benchmark, alcanza con núcleos de
CPU, RAM total y si hay GPU (y su nombre, cuando se puede obtener).

RAM vía ``psutil`` (multiplataforma real, no reimplementado a mano por SO).
GPU es best-effort por SO: cuando no se puede determinar, se informa como
tal en vez de adivinar — una recomendación de modelo basada en una GPU
inventada es peor que una basada en "no se sabe"."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class InfoHardware:
    nucleos_cpu: int
    ram_total_gb: float
    gpu_nombre: str | None  # None: no se pudo determinar (no necesariamente "no hay GPU")


def escanear_hardware() -> InfoHardware:
    import psutil

    return InfoHardware(
        nucleos_cpu=os.cpu_count() or 1,
        ram_total_gb=round(psutil.virtual_memory().total / (1024**3), 1),
        gpu_nombre=_detectar_gpu(),
    )


def _detectar_gpu() -> str | None:
    if sys.platform == "darwin":
        return _detectar_gpu_macos()
    if sys.platform.startswith("linux"):
        return _detectar_gpu_linux()
    if sys.platform == "win32":
        return _detectar_gpu_windows()
    return None


def _detectar_gpu_macos() -> str | None:
    """``system_profiler SPDisplaysDataType -json`` -> primer
    ``_name`` bajo ``SPDisplaysDataType`` — verificado en vivo contra una
    Mac real (devuelve p. ej. "Apple M2 Pro")."""
    import json

    try:
        salida = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        datos = json.loads(salida.stdout)
        tarjetas = datos.get("SPDisplaysDataType", [])
        return tarjetas[0].get("_name") if tarjetas else None
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError, IndexError, KeyError):
        return None


def _detectar_gpu_linux() -> str | None:
    """Best-effort: ``nvidia-smi`` si hay GPU NVIDIA (la más relevante para
    inferencia local), si no ``lspci`` buscando el controlador de video.
    No verificado en vivo (sin máquina Linux disponible en esta sesión) —
    ambos comandos son estándar y ampliamente documentados, pero si fallan
    simplemente no hay recomendación de GPU, nunca una inventada."""
    try:
        salida = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        nombre = salida.stdout.strip().splitlines()
        if nombre:
            return nombre[0]
    except (subprocess.SubprocessError, OSError):
        pass

    try:
        salida = subprocess.run(["lspci"], capture_output=True, text=True, timeout=10, check=True)
        for linea in salida.stdout.splitlines():
            if "VGA" in linea or "3D controller" in linea:
                return linea.split(":", 2)[-1].strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _detectar_gpu_windows() -> str | None:
    """Best-effort vía ``wmic`` (legado pero presente en las versiones de
    Windows que todavía lo incluyen). No verificado en vivo — sin máquina
    Windows disponible en esta sesión; si falla, GPU queda en None, nunca
    inventada."""
    try:
        salida = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "name"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        lineas = [l.strip() for l in salida.stdout.splitlines() if l.strip() and l.strip() != "Name"]
        return lineas[0] if lineas else None
    except (subprocess.SubprocessError, OSError):
        return None
