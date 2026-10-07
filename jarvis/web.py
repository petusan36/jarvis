"""Abrir páginas web a pedido del usuario: una URL concreta, o una búsqueda si
no la da. Para música específicamente en YouTube con autoplay, ver musica.py
— esta herramienta es para todo lo demás (Spotify, noticias, lo que sea).
"""

from __future__ import annotations

import urllib.parse
import webbrowser
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .herramientas import Herramientas

AbrirNavegador = Callable[[str], None]


def registrar_web(h: "Herramientas", abrir_navegador: AbrirNavegador = webbrowser.open) -> None:
    @h.registrar(
        "abrir_pagina_web",
        "Abre una página web en el navegador: una URL si el usuario la da "
        "(p. ej. 'open.spotify.com'), o una búsqueda en Google si no. Para "
        "música en YouTube con reproducción automática, usa mejor "
        "reproducir_musica.",
        {"url_o_busqueda": {"type": "string", "description": "URL completa o términos a buscar."}},
        requiere_dueño=True,
    )
    def abrir_pagina_web(url_o_busqueda: str) -> str:
        texto = url_o_busqueda.strip()
        if not texto:
            raise ValueError("dime qué página abrir o qué buscar")
        url = _a_url(texto)
        abrir_navegador(url)
        return f"Abierto: {url}"


def _a_url(texto: str) -> str:
    if "://" in texto:
        return texto
    if "." in texto.split("/", 1)[0] and " " not in texto:
        return f"https://{texto}"
    return "https://www.google.com/search?q=" + urllib.parse.quote(texto)
