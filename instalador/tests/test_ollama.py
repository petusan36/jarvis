"""Pruebas de la detección e instalación de Ollama (ver
src/instalador/ollama.py), sin UI."""

import shutil
from unittest.mock import MagicMock, patch

import pytest

from instalador import ollama


def test_detecta_ollama_si_esta_en_el_path():
    with patch.object(shutil, "which", return_value="/usr/local/bin/ollama"):
        assert ollama.ollama_instalado() is True


def test_detecta_ollama_por_ruta_conocida_si_no_esta_en_el_path():
    with patch.object(shutil, "which", return_value=None):
        with patch.object(ollama.Path, "is_file", return_value=True):
            assert ollama.ollama_instalado() is True


def test_no_detecta_ollama_si_no_esta_en_ningun_lado():
    with patch.object(shutil, "which", return_value=None):
        with patch.object(ollama.Path, "is_file", return_value=False):
            assert ollama.ollama_instalado() is False


@pytest.mark.parametrize("plataforma,disponible", [("darwin", True), ("linux", True), ("win32", False)])
def test_instalacion_automatica_disponible_segun_so(monkeypatch, plataforma, disponible):
    monkeypatch.setattr(ollama.sys, "platform", plataforma)
    assert ollama.instalar_automatico_disponible() is disponible


def test_instalar_ollama_en_windows_levanta_error_sin_tocar_nada(monkeypatch):
    """Sin flag silencioso confirmado contra fuente oficial: nunca se debe
    intentar instalar solo en Windows (ver docstring del módulo)."""
    monkeypatch.setattr(ollama.sys, "platform", "win32")
    with pytest.raises(ollama.ErrorInstalacionOllama, match="Windows"):
        ollama.instalar_ollama(reportar=lambda _: None)


def test_instalar_ollama_corre_el_script_oficial_y_reporta_progreso(monkeypatch):
    monkeypatch.setattr(ollama.sys, "platform", "darwin")
    proceso_falso = MagicMock()
    proceso_falso.stdout = iter(["Descargando...\n", "Instalando...\n"])
    proceso_falso.wait.return_value = 0
    llamadas = []
    with patch.object(ollama.subprocess, "Popen", return_value=proceso_falso) as popen_falso:
        ollama.instalar_ollama(reportar=llamadas.append)

    comando = popen_falso.call_args[0][0]
    assert comando == ["sh", "-c", f"curl -fsSL {ollama.URL_INSTALL_SH} | sh"]
    assert "Descargando..." in llamadas
    assert "Instalando..." in llamadas


def test_instalar_ollama_si_el_script_falla_levanta_error_con_el_codigo(monkeypatch):
    monkeypatch.setattr(ollama.sys, "platform", "linux")
    proceso_falso = MagicMock()
    proceso_falso.stdout = iter([])
    proceso_falso.wait.return_value = 1
    with patch.object(ollama.subprocess, "Popen", return_value=proceso_falso):
        with pytest.raises(ollama.ErrorInstalacionOllama, match="código 1"):
            ollama.instalar_ollama(reportar=lambda _: None)
