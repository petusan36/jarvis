"""Pruebas de jarvis.__main__._cargar_reconocimiento_voz: qué pasa cuando no
hay voz enrolada todavía (se enrola sola) y cuando hay una voz enrolada pero
el verificador real no carga (sin tocar SpeechBrain ni el micrófono real)."""

import numpy as np
import pytest

from jarvis.__main__ import _cargar_reconocimiento_voz
from jarvis.config import Config
from jarvis.voz.hablante import VerificadorRoto, guardar_referencia, ruta_referencia


def test_sin_voz_enrolada_la_enrola_automaticamente(tmp_path, monkeypatch):
    """El reconocimiento de hablante está habilitado por defecto: si nadie
    enroló su voz todavía, debe quedar activo desde el primer arranque en
    modo voz, no requerir que el usuario descubra y corra
    `jarvis --enrolar-voz` aparte."""
    config = Config(carpeta_datos=tmp_path)

    def _enrolar_falso(cfg, anunciar=print):
        anunciar("probando")
        guardar_referencia(ruta_referencia(cfg.carpeta_datos), np.array([0.1, 0.2], dtype=np.float32))

    monkeypatch.setattr("jarvis.voz.hablante.enrolar_voz_automatico", _enrolar_falso)

    class _VerificadorFalso:
        def __init__(self, umbral):
            self.umbral = umbral

    monkeypatch.setattr("jarvis.voz.hablante.VerificadorHablante", _VerificadorFalso)

    verificador, referencia = _cargar_reconocimiento_voz(config)

    assert isinstance(verificador, _VerificadorFalso)
    assert referencia is not None


def test_sin_voz_enrolada_y_falla_el_enrolamiento_automatico_no_exige_nada(tmp_path, monkeypatch):
    """Si el enrolamiento automático falla (sin soporte instalado, sin
    micrófono disponible), Jarvis no debe trabar el arranque: sigue sin
    exigir identidad hasta que el usuario pueda enrolar su voz."""
    config = Config(carpeta_datos=tmp_path)

    def _falla(cfg, anunciar=print):
        raise OSError("no hay micrófono disponible")

    monkeypatch.setattr("jarvis.voz.hablante.enrolar_voz_automatico", _falla)

    assert _cargar_reconocimiento_voz(config) == (None, None)


def test_reconocimiento_deshabilitado_no_exige_nada_aunque_haya_voz_enrolada(tmp_path):
    guardar_referencia(ruta_referencia(tmp_path), np.array([0.1, 0.2], dtype=np.float32))
    config = Config(carpeta_datos=tmp_path, reconocimiento_voz_habilitado=False)
    assert _cargar_reconocimiento_voz(config) == (None, None)


def test_voz_enrolada_y_verificador_real_falla_cae_a_fallo_cerrado(tmp_path, monkeypatch):
    """Hallazgo de seguridad real: antes, si VerificadorHablante() fallaba
    (dependencia rota, modelo corrupto), esto devolvía (None, None) — es
    decir, "no se exige nada", igual que si el usuario nunca hubiera
    enrolado su voz. Pero el usuario SÍ enroló: una falla del verificador
    real no debe desactivar en silencio el chequeo que pidió."""
    guardar_referencia(ruta_referencia(tmp_path), np.array([0.1, 0.2], dtype=np.float32))
    config = Config(carpeta_datos=tmp_path)

    def _siempre_falla(*_a, **_kw):
        raise RuntimeError("falta instalar speechbrain")

    monkeypatch.setattr("jarvis.voz.hablante.VerificadorHablante", _siempre_falla)

    verificador, referencia = _cargar_reconocimiento_voz(config)

    assert isinstance(verificador, VerificadorRoto)
    assert referencia is not None
    # y de verdad niega, no solo por el tipo:
    assert verificador.coincide(audio=object(), referencia=referencia) is False


def test_voz_enrolada_y_verificador_real_carga_ok(tmp_path, monkeypatch):
    guardar_referencia(ruta_referencia(tmp_path), np.array([0.1, 0.2], dtype=np.float32))
    config = Config(carpeta_datos=tmp_path)

    class _VerificadorFalso:
        def __init__(self, umbral):
            self.umbral = umbral

    monkeypatch.setattr("jarvis.voz.hablante.VerificadorHablante", _VerificadorFalso)

    verificador, referencia = _cargar_reconocimiento_voz(config)

    assert isinstance(verificador, _VerificadorFalso)
    assert referencia is not None
