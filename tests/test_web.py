"""Pruebas de abrir_pagina_web: nunca abre un navegador real."""

import pytest

from jarvis.herramientas import Herramientas


@pytest.fixture
def web(tmp_path):
    return Herramientas(tmp_path, sistema=False)


def test_url_completa_se_abre_tal_cual(monkeypatch, web):
    abiertas = []
    monkeypatch.setattr("jarvis.web.webbrowser.open", lambda url: abiertas.append(url))

    salida, error = web.ejecutar("abrir_pagina_web", {"url_o_busqueda": "https://open.spotify.com"})

    assert not error
    assert abiertas == ["https://open.spotify.com"]
    assert "https://open.spotify.com" in salida


def test_dominio_sin_protocolo_se_completa(monkeypatch, web):
    abiertas = []
    monkeypatch.setattr("jarvis.web.webbrowser.open", lambda url: abiertas.append(url))

    web.ejecutar("abrir_pagina_web", {"url_o_busqueda": "open.spotify.com"})

    assert abiertas == ["https://open.spotify.com"]


def test_texto_sin_dominio_busca_en_google(monkeypatch, web):
    abiertas = []
    monkeypatch.setattr("jarvis.web.webbrowser.open", lambda url: abiertas.append(url))

    web.ejecutar("abrir_pagina_web", {"url_o_busqueda": "mejores playlists para estudiar"})

    assert len(abiertas) == 1
    assert abiertas[0].startswith("https://www.google.com/search?q=")
    assert "mejores+playlists" in abiertas[0] or "mejores%20playlists" in abiertas[0]


def test_busqueda_vacia_falla(web):
    assert web.ejecutar("abrir_pagina_web", {"url_o_busqueda": "   "})[1] is True
