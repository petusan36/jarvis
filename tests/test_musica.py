"""Pruebas de reproducir_musica: nunca abre un navegador real ni llama a la red."""

import json
import urllib.error

import pytest

from jarvis.herramientas import Herramientas
from jarvis.musica import registrar_musica


@pytest.fixture
def musica(tmp_path):
    return Herramientas(tmp_path, sistema=False, youtube_api_key="")


def test_sin_clave_abre_resultados_de_busqueda(musica):
    abiertas = []
    registrar_musica(musica, "", abrir_navegador=abiertas.append)

    salida, error = musica.ejecutar("reproducir_musica", {"busqueda": "Bohemian Rhapsody"})

    assert not error
    assert len(abiertas) == 1
    assert "youtube.com/results" in abiertas[0]
    assert "Bohemian+Rhapsody" in abiertas[0] or "Bohemian%20Rhapsody" in abiertas[0]
    assert "YOUTUBE_API_KEY" in salida


def test_con_clave_y_resultado_reproduce_directo(tmp_path):
    h = Herramientas(tmp_path, sistema=False, youtube_api_key="clave-de-prueba")
    abiertas = []
    registrar_musica(h, "clave-de-prueba", abrir_navegador=abiertas.append,
                     buscar_video=lambda busqueda, clave: "abc123")

    salida, error = h.ejecutar("reproducir_musica", {"busqueda": "Bohemian Rhapsody"})

    assert not error
    assert len(abiertas) == 1
    assert "watch?v=abc123" in abiertas[0] and "autoplay=1" in abiertas[0]
    assert "YOUTUBE_API_KEY" not in salida


def test_con_clave_pero_api_falla_cae_a_resultados(tmp_path):
    h = Herramientas(tmp_path, sistema=False, youtube_api_key="clave-de-prueba")
    abiertas = []
    registrar_musica(h, "clave-de-prueba", abrir_navegador=abiertas.append,
                     buscar_video=lambda busqueda, clave: None)

    salida, error = h.ejecutar("reproducir_musica", {"busqueda": "algo raro"})

    assert not error
    assert "youtube.com/results" in abiertas[0]


def test_busqueda_vacia_falla(musica):
    assert musica.ejecutar("reproducir_musica", {"busqueda": "   "})[1] is True


def test_buscar_primer_video_parsea_respuesta(monkeypatch):
    from jarvis.musica import _buscar_primer_video

    class RespuestaFalsa:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps({"items": [{"id": {"videoId": "xyz789"}}]}).encode()

    monkeypatch.setattr("jarvis.musica.urllib.request.urlopen", lambda *a, **kw: RespuestaFalsa())

    assert _buscar_primer_video("algo", "clave") == "xyz789"


def test_buscar_primer_video_sin_resultados(monkeypatch):
    from jarvis.musica import _buscar_primer_video

    class RespuestaFalsa:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps({"items": []}).encode()

    monkeypatch.setattr("jarvis.musica.urllib.request.urlopen", lambda *a, **kw: RespuestaFalsa())

    assert _buscar_primer_video("algo", "clave") is None


def test_buscar_primer_video_con_error_de_red_no_rompe(monkeypatch):
    from jarvis.musica import _buscar_primer_video

    def reventar(*_a, **_kw):
        raise urllib.error.URLError("sin red")

    monkeypatch.setattr("jarvis.musica.urllib.request.urlopen", reventar)

    assert _buscar_primer_video("algo", "clave") is None
