"""Pruebas de jarvis.voz.habla._limpiar: lo que no debe leerse en voz alta."""

from jarvis.voz.habla import _limpiar


def test_quita_markdown():
    assert _limpiar("**hola** `mundo` # título") == "hola mundo título"


def test_quita_emoji_simple():
    assert _limpiar("Hasta luego, señor. 🕶️") == "Hasta luego, señor."


def test_quita_emoji_con_variation_selector():
    assert _limpiar("¿Necesita algo más? 😏") == "¿Necesita algo más?"


def test_quita_emoji_compuesto_con_zero_width_joiner():
    assert _limpiar("Familia: 👨‍👩‍👧 lista") == "Familia: lista"


def test_quita_emoji_de_simbolos_diversos():
    assert _limpiar("Todo en orden ➡️ listo") == "Todo en orden listo"


def test_texto_sin_emoji_ni_markdown_no_cambia():
    assert _limpiar("Son las 18:42, señor.") == "Son las 18:42, señor."
