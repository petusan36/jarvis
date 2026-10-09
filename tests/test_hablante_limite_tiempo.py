"""Pruebas de jarvis.voz.hablante._grabar_frase_con_limite: el enrolamiento
nunca debe colgarse para siempre si nadie habla (ver docstring de la
función) — a diferencia de Oido en uso normal, que sí debe esperar sin
límite."""

import time
from unittest.mock import patch

import numpy as np
import pytest

from jarvis.voz import hablante


def test_devuelve_lo_que_capture_grabar_frase_con_vad_si_llega_a_tiempo():
    audio_falso = np.zeros(100, dtype="float32")
    with patch("jarvis.voz.oido.grabar_frase_con_vad", return_value=audio_falso):
        resultado = hablante._grabar_frase_con_limite(sensibilidad=3.0, limite_segundos=2)
    assert resultado is audio_falso


def test_si_nadie_habla_corta_con_error_claro_en_vez_de_colgarse():
    def nunca_vuelve(sensibilidad, margen_eco_segundos=0.25):
        time.sleep(5)  # más que el límite de la prueba
        return np.zeros(1, dtype="float32")

    with patch("jarvis.voz.oido.grabar_frase_con_vad", side_effect=nunca_vuelve):
        with pytest.raises(RuntimeError, match="No se detectó tu voz"):
            hablante._grabar_frase_con_limite(sensibilidad=3.0, limite_segundos=0.3)


def test_un_error_real_de_grabacion_se_repropaga_tal_cual():
    with patch("jarvis.voz.oido.grabar_frase_con_vad", side_effect=OSError("sin dispositivo de entrada")):
        with pytest.raises(OSError, match="sin dispositivo de entrada"):
            hablante._grabar_frase_con_limite(sensibilidad=3.0, limite_segundos=2)


def test_usa_un_margen_de_eco_mayor_que_el_default_de_oido():
    """El enrolamiento anuncia "decí algo ahora" por TTS justo antes de
    grabar — más riesgo de cola acústica de la propia voz de Jarvis que en
    el uso normal de Oido. Confirma que _grabar_y_guardar pide ese margen
    más grande, no el default de 0.25s de grabar_frase_con_vad."""
    with patch("jarvis.voz.oido.grabar_frase_con_vad", return_value=np.zeros(1, dtype="float32")) as grabar_falso:
        hablante._grabar_frase_con_limite(sensibilidad=3.0, limite_segundos=2)
    assert grabar_falso.call_args.kwargs["margen_eco_segundos"] == hablante.MARGEN_ECO_ENROLAMIENTO_SEGUNDOS
    assert hablante.MARGEN_ECO_ENROLAMIENTO_SEGUNDOS > 0.25
