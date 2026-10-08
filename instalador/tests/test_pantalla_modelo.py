"""Pruebas de la pantalla de selección de modelo (pantallas/modelo.py).

``listar_modelos_instalados`` se mockea siempre: es una llamada de red real
a la API de Ollama (ver modelos.py) — un test no debe depender de si hay
Ollama corriendo en la máquina que lo ejecuta, ni de qué modelos tenga."""

from unittest.mock import patch

import instalador.pantallas.modelo as modulo
from instalador.hardware import InfoHardware


def _hardware(ram_total_gb=16.0):
    return InfoHardware(nucleos_cpu=8, ram_total_gb=ram_total_gb, gpu_nombre="GPU de prueba")


def _pantalla(ram_total_gb=16.0, instalados=None, **kwargs):
    with patch.object(modulo, "listar_modelos_instalados", return_value=instalados or []):
        return modulo.PantallaModelo(_hardware(ram_total_gb), **kwargs)


def test_sin_nada_instalado_arranca_pidiendo_descargar_el_recomendado():
    p = _pantalla(ram_total_gb=4.0, al_continuar=lambda: None)
    assert p._tag_elegido == "qwen3:1.7b"
    assert p._boton_descargar in p._fila_botones.children
    assert "hace falta descargarlo" in p._estado_label.text


def test_con_el_recomendado_ya_instalado_salta_la_descarga():
    """El caso del usuario: si Ollama ya tiene modelos, hay que preferir
    reusar en vez de empujar una descarga nueva."""
    p = _pantalla(ram_total_gb=16.0, instalados=["qwen3:8b"], al_continuar=lambda: None)
    assert p._tag_elegido == "qwen3:8b"
    assert p._boton_continuar in p._fila_botones.children
    assert p._boton_descargar not in p._fila_botones.children
    assert "listo para usar" in p._estado_label.text


def test_modelo_instalado_mas_chico_que_el_ideal_tambien_se_reusa():
    p = _pantalla(ram_total_gb=16.0, instalados=["qwen3:4b"], al_continuar=lambda: None)
    assert p._tag_elegido == "qwen3:4b"
    assert p._boton_continuar in p._fila_botones.children


def test_botones_marcan_ya_instalado_y_recomendado_por_separado():
    p = _pantalla(ram_total_gb=16.0, instalados=["qwen3:4b"], al_continuar=lambda: None)
    assert "ya instalado" in p._botones_modelo["qwen3:4b"].text
    assert "recomendado" in p._botones_modelo["qwen3:4b"].text
    assert "ya instalado" not in p._botones_modelo["qwen3:8b"].text


def test_elegir_un_modelo_instalado_de_la_lista_salta_la_descarga():
    p = _pantalla(ram_total_gb=16.0, instalados=["qwen3:14b"], al_continuar=lambda: None)
    assert p._boton_descargar in p._fila_botones.children  # arrancó con qwen3:8b, no instalado

    p._elegir_modelo(p._botones_modelo["qwen3:14b"])
    assert p._tag_elegido == "qwen3:14b"
    assert p._boton_continuar in p._fila_botones.children


def test_elegir_un_modelo_no_instalado_de_la_lista_pide_descargar():
    p = _pantalla(ram_total_gb=16.0, instalados=["qwen3:8b"], al_continuar=lambda: None)
    assert p._boton_continuar in p._fila_botones.children  # arrancó con qwen3:8b, instalado

    p._elegir_modelo(p._botones_modelo["qwen3:14b"])
    assert p._tag_elegido == "qwen3:14b"
    assert p._boton_descargar in p._fila_botones.children


def test_descarga_lista_agrega_el_tag_a_instalados_y_habilita_continuar():
    p = _pantalla(ram_total_gb=16.0, instalados=[], al_continuar=lambda: None)
    assert "qwen3:8b" not in p._instalados
    p._descarga_lista()
    assert "qwen3:8b" in p._instalados
    assert p._boton_continuar in p._fila_botones.children
    assert "listo para usar" in p._estado_label.text


def test_descarga_fallo_reactiva_botones_y_muestra_error():
    p = _pantalla(ram_total_gb=16.0, instalados=[], al_continuar=lambda: None)
    for boton in p._botones_modelo.values():
        boton.enabled = False
    p._boton_descargar.enabled = False
    p._descarga_fallo("boom")
    assert p._boton_descargar.enabled is True
    assert all(b.enabled for b in p._botones_modelo.values())
    assert "boom" in p._estado_label.text


def test_continuar_dispara_el_callback():
    llamado = {"listo": False}
    p = _pantalla(ram_total_gb=16.0, al_continuar=lambda: llamado.__setitem__("listo", True))
    p._continuar(None)
    assert llamado["listo"] is True
