"""Pruebas de jarvis.voz.hablante: lo que no necesita el modelo real de SpeechBrain."""

import numpy as np
import pytest

from jarvis.voz.hablante import cargar_referencia, guardar_referencia, similitud_coseno


def test_similitud_coseno_de_un_vector_consigo_mismo_es_uno():
    v = np.array([0.1, 0.4, -0.2, 0.9], dtype=np.float32)
    assert similitud_coseno(v, v) == pytest.approx(1.0)


def test_similitud_coseno_de_vectores_ortogonales_es_cero():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert similitud_coseno(a, b) == pytest.approx(0.0)


def test_similitud_coseno_con_vector_nulo_no_rompe():
    assert similitud_coseno(np.zeros(4), np.ones(4)) == 0.0


def test_guardar_y_cargar_referencia(tmp_path):
    ruta = tmp_path / "voz_dueño.npy"
    embedding = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    guardar_referencia(ruta, embedding)
    cargada = cargar_referencia(ruta)
    assert cargada is not None
    np.testing.assert_allclose(cargada, embedding)


def test_cargar_referencia_sin_enrolar_devuelve_none(tmp_path):
    assert cargar_referencia(tmp_path / "no_existe.npy") is None
