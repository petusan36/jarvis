"""Pruebas de la detección de Ollama (ver src/instalador/ollama.py), sin UI."""

import shutil
from unittest.mock import patch

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
