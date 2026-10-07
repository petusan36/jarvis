"""Buscar y reproducir música o videos de YouTube.

Con YOUTUBE_API_KEY configurada, reproduce directo el primer resultado
(autoplay). Sin ella —o si la búsqueda falla por cualquier motivo—, abre la
página de resultados para que el usuario elija: sigue funcionando, solo sin
el autoplay.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .herramientas import Herramientas

URL_BUSQUEDA_API = "https://www.googleapis.com/youtube/v3/search"
URL_RESULTADOS = "https://www.youtube.com/results"
URL_VIDEO = "https://www.youtube.com/watch"

AbrirNavegador = Callable[[str], None]
BuscarVideo = Callable[[str, str], "str | None"]


def _buscar_primer_video(busqueda: str, clave: str) -> str | None:
    """Mejor esfuerzo: si la API falla (clave inválida, cuota, sin red), no
    rompe la herramienta — simplemente no hay autoplay."""
    parametros = urllib.parse.urlencode({
        "part": "id", "type": "video", "maxResults": 1, "q": busqueda, "key": clave,
    })
    try:
        with urllib.request.urlopen(f"{URL_BUSQUEDA_API}?{parametros}", timeout=10) as respuesta:
            datos = json.loads(respuesta.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None
    elementos = datos.get("items") or []
    return elementos[0]["id"]["videoId"] if elementos else None


def registrar_musica(h: "Herramientas", clave_youtube: str,
                     abrir_navegador: AbrirNavegador = webbrowser.open,
                     buscar_video: BuscarVideo = _buscar_primer_video) -> None:
    @h.registrar(
        "reproducir_musica",
        "Busca una canción, video o artista en YouTube y lo reproduce. Úsala "
        "cuando el usuario pida escuchar o poner música, una canción o un video.",
        {"busqueda": {"type": "string", "description": "Qué buscar, p. ej. 'Bohemian Rhapsody Queen'."}},
        requiere_dueño=True,
    )
    def reproducir_musica(busqueda: str) -> str:
        busqueda = busqueda.strip()
        if not busqueda:
            raise ValueError("dime qué canción o video buscar")

        video_id = buscar_video(busqueda, clave_youtube) if clave_youtube else None
        if video_id:
            parametros = urllib.parse.urlencode({"v": video_id, "autoplay": 1})
            abrir_navegador(f"{URL_VIDEO}?{parametros}")
            return f"Reproduciendo en YouTube: {busqueda}."

        parametros = urllib.parse.urlencode({"search_query": busqueda})
        abrir_navegador(f"{URL_RESULTADOS}?{parametros}")
        if clave_youtube:
            return f"Abiertos los resultados de YouTube para «{busqueda}»."
        return (
            f"Abiertos los resultados de YouTube para «{busqueda}», sin reproducir "
            "directo: no hay YOUTUBE_API_KEY configurada."
        )
