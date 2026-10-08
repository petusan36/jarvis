"""Pruebas de la pantalla de Términos y Condiciones (pantallas/terminos.py)."""

from instalador.pantallas.terminos import PantallaTerminos


def test_boton_continuar_arranca_deshabilitado():
    p = PantallaTerminos(al_aceptar=lambda: None, al_rechazar=lambda: None)
    assert p._boton_continuar.enabled is False


def test_boton_continuar_se_habilita_al_aceptar_checkbox():
    p = PantallaTerminos(al_aceptar=lambda: None, al_rechazar=lambda: None)
    p._checkbox.value = True
    p._actualizar_boton_continuar(None)
    assert p._boton_continuar.enabled is True


def test_continuar_sin_aceptar_checkbox_no_dispara_callback():
    """Defensa real, no solo cosmética: aunque algo llame a _continuar
    directo (botón debería estar deshabilitado, pero no hay que confiar
    solo en eso), sin el checkbox marcado no debe avanzar."""
    llamado = {"aceptado": False}
    p = PantallaTerminos(al_aceptar=lambda: llamado.__setitem__("aceptado", True), al_rechazar=lambda: None)
    p._continuar(None)
    assert llamado["aceptado"] is False


def test_aceptar_con_checkbox_marcado_dispara_al_aceptar():
    llamado = {"aceptado": False}
    p = PantallaTerminos(al_aceptar=lambda: llamado.__setitem__("aceptado", True), al_rechazar=lambda: None)
    p._checkbox.value = True
    p._continuar(None)
    assert llamado["aceptado"] is True


def test_rechazar_dispara_al_rechazar():
    llamado = {"rechazado": False}
    p = PantallaTerminos(al_aceptar=lambda: None, al_rechazar=lambda: llamado.__setitem__("rechazado", True))
    p._rechazar(None)
    assert llamado["rechazado"] is True
