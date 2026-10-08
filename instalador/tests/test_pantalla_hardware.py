"""Pruebas de la pantalla de hardware (pantallas/hardware.py)."""

from unittest.mock import patch

import instalador.pantallas.hardware as modulo
from instalador.hardware import InfoHardware


def _info_falsa(**overrides):
    base = dict(nucleos_cpu=8, ram_total_gb=16.0, gpu_nombre="GPU de prueba")
    base.update(overrides)
    return InfoHardware(**base)


def test_muestra_los_datos_escaneados():
    with patch.object(modulo, "escanear_hardware", return_value=_info_falsa()):
        p = modulo.PantallaHardware(al_continuar=lambda info: None)
    textos = [hijo.text for hijo in p.contenido.children[2].children]
    assert "Núcleos de CPU: 8" in textos
    assert "RAM total: 16.0 GB" in textos
    assert "GPU: GPU de prueba" in textos


def test_gpu_desconocida_se_muestra_como_tal_no_inventada():
    with patch.object(modulo, "escanear_hardware", return_value=_info_falsa(gpu_nombre=None)):
        p = modulo.PantallaHardware(al_continuar=lambda info: None)
    textos = [hijo.text for hijo in p.contenido.children[2].children]
    assert "GPU: no se pudo determinar" in textos


def test_continuar_pasa_la_info_escaneada_al_callback():
    info = _info_falsa()
    recibido = {}
    with patch.object(modulo, "escanear_hardware", return_value=info):
        p = modulo.PantallaHardware(al_continuar=lambda i: recibido.setdefault("info", i))
    p._continuar(None)
    assert recibido["info"] is info
