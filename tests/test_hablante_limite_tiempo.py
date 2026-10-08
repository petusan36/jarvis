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
    def nunca_vuelve(sensibilidad):
        time.sleep(5)  # más que el límite de la prueba
        return np.zeros(1, dtype="float32")

    with patch("jarvis.voz.oido.grabar_frase_con_vad", side_effect=nunca_vuelve):
        with pytest.raises(RuntimeError, match="No se detectó tu voz"):
            hablante._grabar_frase_con_limite(sensibilidad=3.0, limite_segundos=0.3)


def test_un_error_real_de_grabacion_se_repropaga_tal_cual():
    with patch("jarvis.voz.oido.grabar_frase_con_vad", side_effect=OSError("sin dispositivo de entrada")):
        with pytest.raises(OSError, match="sin dispositivo de entrada"):
            hablante._grabar_frase_con_limite(sensibilidad=3.0, limite_segundos=2)
