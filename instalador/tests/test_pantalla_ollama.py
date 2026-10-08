"""Pruebas de la pantalla de Ollama (pantallas/ollama.py): el requisito
bloqueante es lo crítico acá, no solo el texto que muestra."""

from unittest.mock import patch

import instalador.pantallas.ollama as modulo


def test_con_ollama_instalado_muestra_boton_continuar():
    with patch.object(modulo, "ollama_instalado", return_value=True):
        p = modulo.PantallaOllama(al_continuar=lambda: None)
        assert p._boton_continuar in p._fila_botones.children
        assert "instalado" in p._estado_label.text
        assert "no está" not in p._estado_label.text


def test_sin_ollama_no_ofrece_boton_continuar():
    """El bloqueo real: sin Ollama, el botón de continuar ni siquiera está
    en la pantalla — no alcanza con que esté deshabilitado."""
    with patch.object(modulo, "ollama_instalado", return_value=False):
        p = modulo.PantallaOllama(al_continuar=lambda: None)
        assert p._boton_continuar not in p._fila_botones.children
        assert p._boton_instalar in p._fila_botones.children
        assert "no está instalado" in p._estado_label.text


def test_continuar_dispara_callback_solo_si_hay_ollama():
    llamado = {"listo": False}
    with patch.object(modulo, "ollama_instalado", return_value=True):
        p = modulo.PantallaOllama(al_continuar=lambda: llamado.__setitem__("listo", True))
        p._continuar(None)
    assert llamado["listo"] is True


def test_verificar_de_nuevo_refleja_un_cambio_de_estado():
    """Simula instalar Ollama mientras el instalador sigue abierto y
    apretar "Verificar de nuevo": el estado tiene que poder pasar de
    bloqueado a desbloqueado sin reabrir la pantalla."""
    with patch.object(modulo, "ollama_instalado", return_value=False):
        p = modulo.PantallaOllama(al_continuar=lambda: None)
        assert p._boton_continuar not in p._fila_botones.children

    with patch.object(modulo, "ollama_instalado", return_value=True):
        p._verificar(None)
        assert p._boton_continuar in p._fila_botones.children
