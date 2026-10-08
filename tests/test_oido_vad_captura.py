"""Pruebas de jarvis.voz.oido.grabar_frase_con_vad: captura de una frase
por micrófono guiada por el detector de voz (VAD), sin tocar hardware real
(sounddevice.InputStream se mockea)."""

from unittest.mock import patch

import numpy as np

from jarvis.voz.oido import BLOQUE, grabar_frase_con_vad


class _HudFalso:
    def __init__(self):
        self.estados = []
        self.niveles = []

    def estado(self, nombre, texto=None):
        self.estados.append((nombre, texto))

    def nivel(self, valor):
        self.niveles.append(valor)


def _bloque_silencio():
    return np.zeros((BLOQUE, 1), dtype="float32")


def _bloque_voz():
    # RMS bien por encima del umbral mínimo (0.006) para que el detector lo cuente como voz.
    return np.full((BLOQUE, 1), 0.2, dtype="float32")


def _input_stream_falso(bloques):
    """Fábrica de una clase que imita sd.InputStream: en vez de abrir el
    micrófono real, al entrar al `with` entrega a mano los bloques ya
    armados, llamando al callback como lo haría sounddevice de verdad."""

    class _Falso:
        def __init__(self, **kwargs):
            self._callback = kwargs["callback"]

        def __enter__(self):
            for bloque in bloques:
                self._callback(bloque, None, None, None)
            return self

        def __exit__(self, *_a):
            return False

    return _Falso


def test_graba_voz_y_corta_tras_silencio_suficiente():
    """inicio (6 bloques de voz, > bloques_inicio=4) -> silencio (28
    bloques, > bloques_silencio=27) corta la frase — mismos umbrales que
    DetectorVoz por defecto."""
    bloques = [_bloque_voz()] * 6 + [_bloque_silencio()] * 28
    hud = _HudFalso()

    # Primera llamada calcula fin_eco = t0 + 0.25; el resto tiene que caer
    # DESPUÉS de fin_eco para que el bloque "del eco" no se descarte para
    # siempre (si monotonic() quedara fijo, el `continue` del inicio del
    # loop nunca se corta y la cola se vacía sin procesar nada, colgando
    # el test en el próximo .get() sobre una cola vacía).
    avance_reloj = iter([1000.0] + [1000.3] * 100)
    with patch("sounddevice.InputStream", _input_stream_falso(bloques)):
        with patch("jarvis.voz.oido.time.monotonic", side_effect=lambda: next(avance_reloj)):
            audio = grabar_frase_con_vad(sensibilidad=3.0, hud=hud)

    assert isinstance(audio, np.ndarray)
    assert len(audio) > 0
    assert ("escuchando", "") in hud.estados


def test_sin_hud_usa_hudnulo_sin_romper():
    bloques = [_bloque_voz()] * 6 + [_bloque_silencio()] * 28
    avance_reloj = iter([1000.0] + [1000.3] * 100)
    with patch("sounddevice.InputStream", _input_stream_falso(bloques)):
        with patch("jarvis.voz.oido.time.monotonic", side_effect=lambda: next(avance_reloj)):
            audio = grabar_frase_con_vad(sensibilidad=3.0)  # hud=None por defecto
    assert isinstance(audio, np.ndarray)
