"""Pruebas del registro de herramientas y del gate por voz del dueño
(reconocimiento de hablante, ver jarvis.voz.hablante)."""

import pytest

from jarvis.herramientas import Herramientas


@pytest.fixture
def h(tmp_path):
    return Herramientas(tmp_path, sistema=False)


def test_herramienta_sin_requiere_dueño_se_ejecuta_aunque_no_sea_el_dueño(h):
    h.nuevo_turno("qué hora es", es_dueño=False)
    salida, error = h.ejecutar("fecha_y_hora", {})
    assert not error
    assert salida


def test_herramienta_con_requiere_dueño_se_niega_si_no_es_el_dueño(h):
    h.nuevo_turno("guardame una nota: comprar leche", es_dueño=False)
    salida, error = h.ejecutar("guardar_nota", {"texto": "comprar leche"})
    assert not error  # no es un crash, es una negativa deliberada
    assert "no puedo ejecutar" in salida.lower()
    # y de verdad no se guardó nada
    assert h.ejecutar("leer_notas", {})[0] == "No hay notas guardadas."


def test_herramienta_con_requiere_dueño_se_ejecuta_si_es_el_dueño(h):
    h.nuevo_turno("guardame una nota: comprar leche", es_dueño=True)
    salida, error = h.ejecutar("guardar_nota", {"texto": "comprar leche"})
    assert not error
    assert "guardada" in salida.lower()


def test_por_defecto_es_dueño_es_true_sin_reconocimiento_de_voz(h):
    # nuevo_turno sin especificar es_dueño: comportamiento histórico (modo
    # texto, o voz sin verificador configurado).
    h.nuevo_turno("guardame una nota: comprar pan")
    salida, error = h.ejecutar("guardar_nota", {"texto": "comprar pan"})
    assert not error
    assert "guardada" in salida.lower()


def test_cerrar_jarvis_requiere_dueño(h):
    h.nuevo_turno("cerrate", es_dueño=False)
    salida, error = h.ejecutar("cerrar_jarvis", {})
    assert not error
    assert not h.salir_pedido
    assert "no puedo ejecutar" in salida.lower()
