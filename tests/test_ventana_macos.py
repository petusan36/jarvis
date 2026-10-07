"""Pruebas de la geometría y disponibilidad de la ventana flotante.

No se prueba la ventana real (necesita sesión gráfica) — eso se valida a mano.
"""

from jarvis.hud.ventana_macos import MARGEN, TAMANO_MAXIMO, TAMANO_MINIMO, calcular_geometria, disponible


def test_geometria_arriba_a_la_izquierda_con_margen():
    x, y, ancho, alto = calcular_geometria(1800, 1169)
    assert x == MARGEN
    assert y == 1169 - alto - MARGEN  # "arriba" en Cocoa es alto_pantalla - alto - margen
    assert ancho == alto  # cuadrada


def test_geometria_proporcional_dentro_de_los_limites():
    x, y, ancho, alto = calcular_geometria(1800, 1169)
    assert TAMANO_MINIMO <= ancho <= TAMANO_MAXIMO
    assert ancho == 1800 * 0.18


def test_geometria_respeta_minimo_en_pantalla_chica():
    _, _, ancho, _ = calcular_geometria(1024, 768)
    assert ancho == TAMANO_MINIMO


def test_geometria_respeta_maximo_en_pantalla_grande():
    _, _, ancho, _ = calcular_geometria(5120, 2880)
    assert ancho == TAMANO_MAXIMO


def test_no_disponible_fuera_de_macos(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    assert disponible() is False


def test_no_disponible_si_falta_pyobjc(monkeypatch):
    import builtins

    monkeypatch.setattr("sys.platform", "darwin")
    original_import = builtins.__import__

    def import_falso(nombre, *args, **kwargs):
        if nombre in ("AppKit", "WebKit"):
            raise ImportError(nombre)
        return original_import(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_falso)
    assert disponible() is False


def test_disponible_en_macos_con_pyobjc_instalado(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    assert disponible() is True
