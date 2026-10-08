"""Pruebas de la pantalla final (pantallas/final.py)."""

from pathlib import Path
from unittest.mock import patch

import instalador.pantallas.final as modulo


def test_cerrar_dispara_al_cerrar_sin_abrir_nada():
    llamadas = {"cerrado": False}
    with patch.object(modulo, "abrir_jarvis") as abrir_falso:
        p = modulo.PantallaFinal(Path("/tmp/Jarvis.app"), al_cerrar=lambda: llamadas.__setitem__("cerrado", True))
        p._cerrar(None)
    abrir_falso.assert_not_called()
    assert llamadas["cerrado"] is True


def test_abrir_llama_a_abrir_jarvis_con_el_resultado_y_cierra():
    llamadas = {"cerrado": False}
    resultado = Path("/tmp/Jarvis.app")
    with patch.object(modulo, "abrir_jarvis") as abrir_falso:
        p = modulo.PantallaFinal(resultado, al_cerrar=lambda: llamadas.__setitem__("cerrado", True))
        p._abrir(None)
    abrir_falso.assert_called_once_with(resultado)
    assert llamadas["cerrado"] is True
