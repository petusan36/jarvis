"""Pruebas de recomendación y descarga de modelo (ver src/instalador/modelos.py)."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from instalador import modelos


@pytest.mark.parametrize("ram_gb,esperado", [
    (1, "qwen3:0.6b"),
    (2, "qwen3:0.6b"),
    (4, "qwen3:1.7b"),
    (7.9, "qwen3:1.7b"),
    (8, "qwen3:4b"),
    (16, "qwen3:8b"),
    (32, "qwen3:14b"),
    (128, "qwen3:14b"),  # nunca recomienda más de 14b por defecto
])
def test_recomendar_modelo_segun_ram(ram_gb, esperado):
    assert modelos.recomendar_modelo(ram_gb) == esperado


def test_listar_modelos_instalados_lee_la_api_real_de_ollama():
    respuesta_falsa = MagicMock()
    respuesta_falsa.read.return_value = b'{"models": [{"name": "qwen3:8b"}, {"name": "nomic-embed-text:latest"}]}'
    respuesta_falsa.__enter__.return_value = respuesta_falsa
    with patch.object(modelos.urllib.request, "urlopen", return_value=respuesta_falsa) as urlopen_falso:
        resultado = modelos.listar_modelos_instalados()

    assert urlopen_falso.call_args[0][0] == modelos.URL_TAGS_OLLAMA
    assert resultado == ["qwen3:8b", "nomic-embed-text:latest"]


def test_listar_modelos_instalados_sin_ollama_corriendo_devuelve_lista_vacia():
    with patch.object(modelos.urllib.request, "urlopen", side_effect=modelos.urllib.error.URLError("no conecta")):
        assert modelos.listar_modelos_instalados() == []


@pytest.mark.parametrize("ram_gb,instalados,tag_esperado,ya_instalado_esperado", [
    (16, ["qwen3:8b"], "qwen3:8b", True),          # ya instalado, exacto para la RAM
    (16, ["qwen3:4b"], "qwen3:4b", True),           # instalado pero más chico que el ideal: igual se reusa
    (16, [], "qwen3:8b", False),                     # nada instalado: recomendación normal, hace falta bajar
    (16, ["nomic-embed-text:latest"], "qwen3:8b", False),  # instalado algo ajeno a la familia: no cuenta
    (4, ["qwen3:8b"], "qwen3:1.7b", False),         # instalado pero NO entra en esta RAM: no se usa igual
])
def test_mejor_modelo_prefiere_lo_ya_instalado_que_entra_en_la_ram(
    ram_gb, instalados, tag_esperado, ya_instalado_esperado
):
    assert modelos.mejor_modelo(ram_gb, instalados) == (tag_esperado, ya_instalado_esperado)


def test_descargar_modelo_corre_ollama_pull_y_reporta_progreso():
    proceso_falso = MagicMock()
    proceso_falso.__enter__.return_value = proceso_falso  # como el Popen real: `with` devuelve self
    proceso_falso.stdout = iter(["pulling manifest\n", "verifying sha256\n"])
    proceso_falso.wait.return_value = 0
    llamadas = []
    with patch.object(modelos.subprocess, "Popen", return_value=proceso_falso) as popen_falso:
        modelos.descargar_modelo("qwen3:4b", reportar=llamadas.append)

    assert popen_falso.call_args[0][0] == ["ollama", "pull", "qwen3:4b"]
    assert "pulling manifest" in llamadas
    assert "verifying sha256" in llamadas


def test_descargar_modelo_si_falla_levanta_error_con_codigo():
    proceso_falso = MagicMock()
    proceso_falso.__enter__.return_value = proceso_falso
    proceso_falso.stdout = iter([])
    proceso_falso.wait.return_value = 1
    with patch.object(modelos.subprocess, "Popen", return_value=proceso_falso):
        with pytest.raises(modelos.ErrorDescargaModelo, match="código 1"):
            modelos.descargar_modelo("qwen3:4b", reportar=lambda _: None)


def test_descargar_modelo_sin_ollama_instalado_levanta_error():
    with patch.object(modelos.subprocess, "Popen", side_effect=OSError("no such file")):
        with pytest.raises(modelos.ErrorDescargaModelo):
            modelos.descargar_modelo("qwen3:4b", reportar=lambda _: None)
