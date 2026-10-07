"""Reconocimiento de hablante: verifica si una grabación es la voz del
usuario dueño de Jarvis (roadmap, punto 4).

Usa un modelo neuronal preentrenado de verificación de hablante (SpeechBrain
ECAPA-TDNN, ``speechbrain/spkrec-ecapa-voxceleb``): local, descarga el modelo
(unos 80 MB) solo la primera vez, igual que Whisper o Kokoro.

Flujo:

1. Enrolamiento (una vez): se grava una frase de referencia del usuario y se
   guarda su "huella de voz" (embedding) en ``~/.jarvis/voz_dueño.npy`` (ver
   ``ruta_referencia`` en config.py).
2. En cada frase que Jarvis escuche (``Oido.escuchar``), calcula su embedding
   y lo compara por similitud coseno contra el enrolado. Por encima del
   umbral: es la voz dueña. Por debajo: no lo es, y las herramientas
   marcadas con ``requiere_dueño=True`` (ver herramientas.py) se niegan a
   ejecutarse — Jarvis lo explica y sigue escuchando.

Umbral provisional: no pudo calibrarse con voces humanas reales distintas en
esta tarea (sin micrófono en el entorno de desarrollo, solo verificado que el
modelo carga y produce embeddings comparables). Si Jarvis rechaza tu propia
voz, o acepta la de otra persona, ajustá JARVIS_VOZ_UMBRAL en ~/.jarvis/.env.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

MODELO = "speechbrain/spkrec-ecapa-voxceleb"
UMBRAL_POR_DEFECTO = 0.75


class NoInstalado(RuntimeError):
    """Falta el soporte de reconocimiento de hablante."""


class VerificadorHablante:
    """Compara una grabación contra la voz de referencia del dueño."""

    def __init__(self, umbral: float = UMBRAL_POR_DEFECTO, carpeta_modelo: Path | None = None):
        try:
            from speechbrain.inference.speaker import EncoderClassifier
        except ImportError as error:
            raise NoInstalado(
                "Falta el reconocimiento de voz: pip install -e ."
            ) from error
        self.umbral = umbral
        self._clasificador = EncoderClassifier.from_hparams(
            source=MODELO, savedir=str(carpeta_modelo or _carpeta_modelo_por_defecto())
        )

    def embedding(self, audio: np.ndarray) -> np.ndarray:
        """Huella de voz de una grabación (mono, 16 kHz, float32 en [-1, 1])."""
        import torch

        tensor = torch.from_numpy(np.asarray(audio, dtype=np.float32)).unsqueeze(0)
        with torch.no_grad():
            resultado = self._clasificador.encode_batch(tensor)
        return resultado.squeeze().numpy()

    def coincide(self, audio: np.ndarray, referencia: np.ndarray) -> bool:
        """¿La voz de ``audio`` es la de ``referencia``, según el umbral?"""
        return similitud_coseno(self.embedding(audio), referencia) >= self.umbral


def similitud_coseno(a: np.ndarray, b: np.ndarray) -> float:
    norma = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / norma) if norma else 0.0


def guardar_referencia(ruta: Path, embedding: np.ndarray) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    np.save(ruta, embedding)


def cargar_referencia(ruta: Path) -> np.ndarray | None:
    """None si todavía no hay enrolamiento (Jarvis no exige nada hasta entonces)."""
    return np.load(ruta) if ruta.is_file() else None


def _carpeta_modelo_por_defecto() -> Path:
    return Path.home() / ".jarvis" / "modelos" / "spkrec-ecapa"


def ruta_referencia(carpeta_datos: Path) -> Path:
    return carpeta_datos / "voz_dueño.npy"


def enrolar_voz(config) -> Path:
    """Graba una frase de referencia por el micrófono y la guarda como la voz
    del dueño de Jarvis. Pensado para ``jarvis --enrolar-voz`` (ver
    __main__.py): CLI directa, no pasa por Oido (que ya asume un verificador
    configurado, justo lo que esto crea)."""
    import sounddevice as sd

    frecuencia = 16000
    segundos = 6
    input(f"🎙  Pulsa Enter y hablá sin parar unos {segundos} segundos (cualquier frase sirve)...")
    print("⏺  Grabando...")
    audio = sd.rec(int(segundos * frecuencia), samplerate=frecuencia, channels=1, dtype="float32")
    sd.wait()
    audio = audio[:, 0]

    verificador = VerificadorHablante(umbral=config.umbral_voz_dueño)
    embedding = verificador.embedding(audio)
    ruta = ruta_referencia(config.carpeta_datos)
    guardar_referencia(ruta, embedding)
    print(f"Listo: voz de referencia guardada en {ruta}.")
    return ruta
