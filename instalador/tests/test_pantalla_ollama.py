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


def test_instalar_en_so_sin_soporte_no_arranca_hilo_ni_cambia_botones():
    with patch.object(modulo, "ollama_instalado", return_value=False):
        p = modulo.PantallaOllama(al_continuar=lambda: None)
    with patch.object(modulo, "instalar_automatico_disponible", return_value=False):
        p._instalar(None)
    assert p._boton_instalar.enabled is True
    assert "no está disponible" in p._estado_label.text


def test_instalacion_lista_reactiva_botones_y_reconsulta_estado():
    with patch.object(modulo, "ollama_instalado", return_value=False):
        p = modulo.PantallaOllama(al_continuar=lambda: None)
    p._boton_instalar.enabled = False
    p._boton_verificar.enabled = False
    with patch.object(modulo, "ollama_instalado", return_value=True):
        p._instalacion_lista()
    assert p._boton_instalar.enabled is True
    assert p._boton_continuar in p._fila_botones.children


def test_instalacion_fallo_muestra_el_error_y_reactiva_botones():
    with patch.object(modulo, "ollama_instalado", return_value=False):
        p = modulo.PantallaOllama(al_continuar=lambda: None)
    p._boton_instalar.enabled = False
    p._instalacion_fallo("boom")
    assert p._boton_instalar.enabled is True
    assert "boom" in p._estado_label.text


def test_actualizar_progreso_refleja_la_linea_recibida():
    with patch.object(modulo, "ollama_instalado", return_value=False):
        p = modulo.PantallaOllama(al_continuar=lambda: None)
    p._actualizar_progreso("Descargando Ollama...")
    assert p._estado_label.text == "Descargando Ollama..."


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
