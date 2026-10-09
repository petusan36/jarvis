"""Pruebas de jarvis.conexion_ia._asegurar_ollama_corriendo: la memoria
permanente requiere Ollama corriendo, pero nadie lo arranca a mano hoy — si
no responde, Jarvis intenta levantarlo solo en vez de degradar en silencio
(ver cerebro.py, _contexto_memoria)."""

from unittest.mock import patch

import pytest

from jarvis import conexion_ia


def test_si_ollama_ya_responde_no_hace_nada():
    with patch("jarvis.conexion_ia.listar_modelos_ollama", return_value=["qwen3:8b"]) as listar:
        with patch("jarvis.conexion_ia.subprocess.Popen") as popen:
            conexion_ia._asegurar_ollama_corriendo("http://localhost:11434")
    listar.assert_called_once_with("http://localhost:11434")
    popen.assert_not_called()


def test_si_no_responde_lo_arranca_y_espera_a_que_aparezca():
    respuestas = iter([OSError("no conecta"), OSError("no conecta"), ["qwen3:8b"]])

    def listar_falso(url):
        resultado = next(respuestas)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    with patch("jarvis.conexion_ia.listar_modelos_ollama", side_effect=listar_falso):
        with patch("jarvis.conexion_ia.subprocess.Popen") as popen:
            with patch("jarvis.conexion_ia.time.sleep"):
                conexion_ia._asegurar_ollama_corriendo("http://localhost:11434")
    popen.assert_called_once_with(
        ["ollama", "serve"], stdout=conexion_ia.subprocess.DEVNULL, stderr=conexion_ia.subprocess.DEVNULL
    )


def test_si_el_binario_no_esta_instalado_no_rompe(capsys):
    with patch("jarvis.conexion_ia.listar_modelos_ollama", side_effect=OSError("no conecta")):
        with patch("jarvis.conexion_ia.subprocess.Popen", side_effect=FileNotFoundError):
            conexion_ia._asegurar_ollama_corriendo("http://localhost:11434")
    assert "no está instalado" in capsys.readouterr().out


def test_si_nunca_levanta_avisa_y_no_rompe(capsys):
    with patch("jarvis.conexion_ia.listar_modelos_ollama", side_effect=OSError("no conecta")):
        with patch("jarvis.conexion_ia.subprocess.Popen"):
            with patch("jarvis.conexion_ia.time.sleep"):
                with patch(
                    "jarvis.conexion_ia.time.monotonic", side_effect=[0.0, 0.1, 100.0]
                ):
                    conexion_ia._asegurar_ollama_corriendo("http://localhost:11434")
    assert "no respondió" in capsys.readouterr().out


def test_crear_memoria_llama_a_asegurar_ollama_antes_de_construir():
    config = __import__("jarvis.config", fromlist=["Config"]).Config()
    with patch("jarvis.conexion_ia._asegurar_ollama_corriendo") as asegurar:
        with patch("jarvis.memoria.AdaptadorMemoriaGraphiti") as adaptador:
            conexion_ia._crear_memoria(config)
    asegurar.assert_called_once_with(config.ollama_url)
    adaptador.assert_called_once()
