"""Pruebas de la pantalla de instalación (pantallas/instalacion.py)."""

from pathlib import Path

import instalador.pantallas.instalacion as modulo


def test_instalacion_lista_guarda_el_resultado_y_habilita_continuar():
    p = modulo.PantallaInstalacion(al_continuar=lambda resultado: None)
    resultado = Path("/tmp/Jarvis.app")
    p._instalacion_lista(resultado)
    assert p._resultado == resultado
    assert p._boton_continuar in p._fila_botones.children
    assert "instalado" in p._estado_label.text


def test_instalacion_fallo_reactiva_boton_y_muestra_error():
    p = modulo.PantallaInstalacion(al_continuar=lambda resultado: None)
    p._boton_instalar.enabled = False
    p._instalacion_fallo("boom")
    assert p._boton_instalar.enabled is True
    assert "boom" in p._estado_label.text


def test_continuar_pasa_el_resultado_guardado_al_callback():
    recibido = {}
    p = modulo.PantallaInstalacion(al_continuar=lambda resultado: recibido.setdefault("r", resultado))
    resultado = Path("/tmp/Jarvis.app")
    p._instalacion_lista(resultado)
    p._continuar(None)
    assert recibido["r"] == resultado


def test_actualizar_progreso_refleja_la_linea():
    p = modulo.PantallaInstalacion(al_continuar=lambda resultado: None)
    p._actualizar_progreso("Descargando Jarvis...")
    assert p._estado_label.text == "Descargando Jarvis..."
