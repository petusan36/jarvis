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

Umbral: bajado dos veces con datos reales, no a ciegas. Primero de 0,75 a
0,55 (0,75 ya rechazaba al dueño el 100% de las veces). Con el log de
similitud real (ver jarvis.voz.oido._coincide_con_dueño) se midieron tres
turnos reales de la MISMA persona enrolada: 0.513, 0.508, 0.412 — todos por
debajo de 0,55 también. Bajado a 0,40 para cubrir ese rango observado. Sigue
sin ser un valor calibrado con un dataset real de voces distintas (no hay
medición de cuánto sube el riesgo de aceptar a un impostor al bajar el
umbral) — es la mejor estimación posible con los datos de uso real
disponibles hasta ahora. Si Jarvis rechaza tu propia voz, o acepta la de
otra persona, ajustá JARVIS_VOZ_UMBRAL en ~/.jarvis/.env con el número que
el log te muestre en cada rechazo.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

MODELO = "speechbrain/spkrec-ecapa-voxceleb"
UMBRAL_POR_DEFECTO = 0.40


class NoInstalado(RuntimeError):
    """Falta el soporte de reconocimiento de hablante."""


class VerificadorRoto:
    """Se usa cuando SÍ hay una voz enrolada pero el verificador real no
    pudo cargar (dependencia rota, modelo corrupto, sin espacio en disco,
    etc.) — a diferencia de no pasar ningún verificador (nadie enroló nada
    todavía, no se exige nada), acá el usuario SÍ optó por el
    reconocimiento de voz. Fallar cerrado, no abierto: mientras el
    verificador real no cargue, cualquier herramienta con
    ``requiere_dueño=True`` se niega para cualquier voz, en vez de
    ejecutarse para todas como si nunca se hubiera enrolado nada."""

    def coincide(self, audio: np.ndarray, referencia: np.ndarray) -> bool:
        return False


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

    def similitud(self, audio: np.ndarray, referencia: np.ndarray) -> float:
        """Similitud coseno cruda entre ``audio`` y ``referencia``, sin
        aplicar el umbral — expuesto aparte de ``coincide`` para poder
        registrar el valor real y calibrar JARVIS_VOZ_UMBRAL con datos de
        uso real en vez de a ciegas (ver UMBRAL_POR_DEFECTO)."""
        return similitud_coseno(self.embedding(audio), referencia)

    def coincide(self, audio: np.ndarray, referencia: np.ndarray) -> bool:
        """¿La voz de ``audio`` es la de ``referencia``, según el umbral?"""
        return self.similitud(audio, referencia) >= self.umbral


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
    __main__.py): CLI directa para re-enrolar a mano cuando se quiera
    reemplazar la referencia existente."""
    input("🎙  Pulsa Enter y hablá sin parar unos segundos (cualquier frase sirve)...")
    return _grabar_y_guardar(config)


def enrolar_voz_automatico(config, anunciar=print) -> Path:
    """Como ``enrolar_voz``, pero sin esperar una tecla: graba automáticamente
    tras un conteo. Se usa al arrancar Jarvis en modo voz cuando el
    reconocimiento de hablante está habilitado (por defecto) y todavía no hay
    ninguna voz enrolada — así queda activo desde el primer uso, sin que el
    usuario tenga que descubrir y correr ``--enrolar-voz`` por separado (ni
    hay terminal real para pulsar Enter cuando Jarvis corre como app de
    escritorio sin consola). ``anunciar``: cómo avisarle al usuario (por
    defecto ``print``; quien llame puede pasar también la síntesis de voz)."""
    import time

    anunciar("🎙  Para identificar su voz, grabo una muestra en 3 segundos — hable con naturalidad.")
    time.sleep(3)
    return _grabar_y_guardar(config)


def _grabar_y_guardar(config, segundos: int = 6) -> Path:
    import sounddevice as sd

    frecuencia = 16000
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
