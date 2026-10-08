"""Recomendación y descarga de modelo local, sin UI.

Tags verificados contra la librería real de Ollama (ollama.com/library/qwen3,
2026-10-08) — no inventados. Se usa la familia Qwen3 por consistencia con el
resto de Jarvis (``jarvis/config.py::memoria_modelo_llm`` ya usa
``qwen3:4b``), no por capricho.

La recomendación se basa en RAM total, con margen generoso: el tamaño de
descarga de un modelo es un piso razonable de cuánta RAM hace falta para
correrlo con margen (no es una medición de uso real en inferencia, que
varía con cuantización y contexto activo — alcanza como heurística para
no recomendar algo que ni siquiera va a cargar)."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

URL_TAGS_OLLAMA = "http://localhost:11434/api/tags"


@dataclass(frozen=True)
class OpcionModelo:
    tag: str
    tamano_gb: float
    ram_minima_gb: float


# Orden de menor a mayor: _recomendar_modelo recorre de atrás para adelante
# y se queda con el primero que entra en la RAM disponible.
MODELOS_DISPONIBLES = [
    OpcionModelo("qwen3:0.6b", 0.5, 2),
    OpcionModelo("qwen3:1.7b", 1.4, 4),
    OpcionModelo("qwen3:4b", 2.5, 8),
    OpcionModelo("qwen3:8b", 5.2, 16),
    OpcionModelo("qwen3:14b", 9.3, 32),
]


def recomendar_modelo(ram_total_gb: float) -> str:
    """El modelo más grande (mejor calidad) que entra con margen en la RAM
    disponible. Nunca recomienda más que qwen3:14b por defecto, aunque haya
    RAM de sobra: para un asistente de voz, latencia importa más que un
    modelo más grande todavía — ver MODELOS_DISPONIBLES para elegir manual
    uno más grande si se quiere."""
    elegido = MODELOS_DISPONIBLES[0]
    for opcion in MODELOS_DISPONIBLES:
        if ram_total_gb >= opcion.ram_minima_gb:
            elegido = opcion
    return elegido.tag


def listar_modelos_instalados() -> list[str]:
    """Modelos que Ollama ya tiene descargados en este equipo — si Ollama
    está instalado, lo más probable es que ya tenga algo (quien lo instaló
    por su cuenta antes de correr este instalador, o una instalación previa
    de Jarvis). Mismo endpoint que usa el propio Jarvis
    (jarvis/proveedores/ollama_adaptador.py::listar_modelos_ollama) — no
    corre ``ollama list`` como subproceso para no depender de parsear su
    salida de texto. Lista vacía si Ollama no está corriendo o no responde:
    no es un error acá, solo significa "no hay nada que reusar todavía"."""
    try:
        with urllib.request.urlopen(URL_TAGS_OLLAMA, timeout=5) as respuesta:
            datos = json.loads(respuesta.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return []
    return [m["name"] for m in datos.get("models", [])]


def mejor_modelo(ram_total_gb: float, instalados: list[str]) -> tuple[str, bool]:
    """¿Cuál usar? Si ya hay un modelo conocido (``MODELOS_DISPONIBLES``)
    instalado que entra en la RAM disponible, se prefiere el más grande de
    esos — reusar lo que ya está en el equipo, no bajar algo nuevo por
    reflejo. Devuelve ``(tag, ya_instalado)``: si ``ya_instalado`` es
    ``False``, hace falta ``descargar_modelo`` antes de poder usarlo."""
    elegido = None
    for opcion in MODELOS_DISPONIBLES:
        if opcion.tag in instalados and ram_total_gb >= opcion.ram_minima_gb:
            elegido = opcion
    if elegido is not None:
        return elegido.tag, True
    return recomendar_modelo(ram_total_gb), False


class ErrorDescargaModelo(RuntimeError):
    """``ollama pull`` falló o Ollama no está disponible."""


def descargar_modelo(tag: str, reportar: Callable[[str], None]) -> None:
    """Corre ``ollama pull <tag>`` real, reportando cada línea de progreso.
    Bloqueante: pensado para un hilo aparte (ver pantallas/modelo.py), igual
    que ``ollama.instalar_ollama``."""
    reportar(f"Descargando {tag}...")
    try:
        proceso_cm = subprocess.Popen(
            ["ollama", "pull", tag],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as error:
        raise ErrorDescargaModelo(f"No se pudo iniciar la descarga: {error}") from error

    # `with` cierra el pipe de stdout solo, incluso si algo entre medio
    # lanza una excepción — sin esto, cada descarga deja un file descriptor
    # abierto (confirmado con ResourceWarning en una corrida real).
    with proceso_cm as proceso:
        assert proceso.stdout is not None
        for linea in proceso.stdout:
            linea = linea.strip()
            if linea:
                reportar(linea)
        codigo = proceso.wait()

    if codigo != 0:
        raise ErrorDescargaModelo(f"La descarga de {tag} terminó con error (código {codigo}).")
