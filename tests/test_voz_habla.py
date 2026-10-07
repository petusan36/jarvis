"""Tests de jarvis.voz.habla con audio sintético (sin cargar modelos de TTS)."""

import numpy as np

from jarvis.voz.habla import _recortar_cola_fantasma

FRECUENCIA = 24000


def _tramo(segundos: float, amplitud: float) -> np.ndarray:
    n = int(FRECUENCIA * segundos)
    return np.full(n, amplitud, dtype=np.float32)


def test_recorta_rafaga_fantasma_tras_silencio_de_cierre():
    # habla fuerte -> silencio real -> ráfaga fantasma débil -> silencio final
    habla = _tramo(1.0, 0.8)
    silencio = _tramo(0.1, 0.01)
    rafaga = _tramo(0.2, 0.15)
    cola = _tramo(0.1, 0.0)
    audio = np.concatenate([habla, silencio, rafaga, cola])

    recortado = _recortar_cola_fantasma(audio, np, FRECUENCIA)

    # se corta en o antes del silencio real (fin del habla), nunca incluye la ráfaga
    assert len(recortado) <= len(habla) + len(silencio)
    assert len(recortado) >= len(habla)


def test_no_recorta_pausas_intermedias_entre_oraciones():
    # pausa breve entre dos oraciones, ambas con habla fuerte real: no debe cortar nada
    primera = _tramo(1.0, 0.8)
    pausa = _tramo(0.1, 0.01)
    segunda = _tramo(1.0, 0.8)
    audio = np.concatenate([primera, pausa, segunda])

    recortado = _recortar_cola_fantasma(audio, np, FRECUENCIA)

    assert len(recortado) == len(audio)


def test_audio_vacio_no_rompe():
    assert len(_recortar_cola_fantasma(np.array([], dtype=np.float32), np, FRECUENCIA)) == 0


def test_audio_silencioso_no_rompe():
    silencio = _tramo(0.5, 0.0)
    assert len(_recortar_cola_fantasma(silencio, np, FRECUENCIA)) == len(silencio)
