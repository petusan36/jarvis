"""Reconocimiento de hablante: verifica si una grabación es la voz del
usuario dueño de Jarvis (roadmap, punto 4).

Usa un modelo neuronal preentrenado de verificación de hablante (SpeechBrain
ECAPA-TDNN, ``speechbrain/spkrec-ecapa-voxceleb``): local, descarga el modelo
(unos 80 MB) solo la primera vez, igual que Whisper o Kokoro.

Flujo:

1. Enrolamiento (una vez): se graban varias frases cortas de referencia del
   usuario (ver ``N_FRASES_ENROLAMIENTO``) y se guarda el PROMEDIO de sus
   "huellas de voz" (embeddings) en ``~/.jarvis/voz_dueño.npy`` (ver
   ``ruta_referencia`` en config.py).
2. En cada frase que Jarvis escuche (``Oido.escuchar``), calcula su embedding
   y lo compara por similitud coseno contra el enrolado. Por encima del
   umbral: es la voz dueña. Por debajo: no lo es, y las herramientas
   marcadas con ``requiere_dueño=True`` (ver herramientas.py) se niegan a
   ejecutarse — Jarvis lo explica y sigue escuchando.

Causa raíz real encontrada (no solo ajuste de umbral): el enrolamiento
grababa una ÚNICA toma continua de 6s con ``sd.rec()`` directo, mientras que
la verificación en uso real compara contra frases cortas recortadas por VAD
(``Oido._grabar_continuo``) — formatos de audio distintos. Esa discrepancia
por sí sola degradaba la similitud real (medida en vivo: 0.22-0.39) por
debajo de cualquier umbral razonable, sin importar cuánto se bajara. Fix:
el enrolamiento ahora graba con el mismo mecanismo de VAD que el uso real
(``jarvis.voz.oido.grabar_frase_con_vad``), varias frases cortas, y promedia
sus embeddings — así la referencia queda en las mismas condiciones que lo
que se va a comparar después.

Umbral: bajado dos veces con datos reales antes de encontrar la causa real
de arriba. Primero de 0,75 a 0,55 (0,75 ya rechazaba al dueño el 100% de las
veces), después a 0,40. Con el fix del enrolamiento la similitud real
debería subir bastante — si Jarvis sigue rechazando tu propia voz, o acepta
la de otra persona, ajustá JARVIS_VOZ_UMBRAL en ~/.jarvis/.env con el número
que el log te muestre en cada rechazo (ver
jarvis.voz.oido._coincide_con_dueño).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

MODELO = "speechbrain/spkrec-ecapa-voxceleb"
UMBRAL_POR_DEFECTO = 0.40
N_FRASES_ENROLAMIENTO = 3  # promediar varias frases da una huella más estable que una sola toma


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
    """Graba varias frases cortas de referencia por el micrófono (con el
    mismo detector de voz que el uso real) y guarda el promedio como la voz
    del dueño de Jarvis. Pensado para ``jarvis --enrolar-voz`` (ver
    __main__.py): CLI directa para re-enrolar a mano cuando se quiera
    reemplazar la referencia existente."""
    input(f"🎙  Pulsa Enter: vamos a grabar {N_FRASES_ENROLAMIENTO} frases cortas para reconocer tu voz...")
    return _grabar_y_guardar(config, anunciar=print)


def enrolar_voz_automatico(config, anunciar=print) -> Path:
    """Como ``enrolar_voz``, pero sin esperar una tecla: arranca automático
    tras un conteo. Se usa al arrancar Jarvis en modo voz cuando el
    reconocimiento de hablante está habilitado (por defecto) y todavía no hay
    ninguna voz enrolada — así queda activo desde el primer uso, sin que el
    usuario tenga que descubrir y correr ``--enrolar-voz`` por separado (ni
    hay terminal real para pulsar Enter cuando Jarvis corre como app de
    escritorio sin consola). ``anunciar``: cómo avisarle al usuario (por
    defecto ``print``; quien llame puede pasar también la síntesis de voz)."""
    import time

    anunciar(
        f"🎙  Para identificar su voz, voy a grabar {N_FRASES_ENROLAMIENTO} frases cortas — "
        "hable con naturalidad después de cada aviso."
    )
    time.sleep(3)
    return _grabar_y_guardar(config, anunciar=anunciar)


def _grabar_y_guardar(config, anunciar=print) -> Path:
    """Graba ``N_FRASES_ENROLAMIENTO`` frases con
    ``jarvis.voz.oido.grabar_frase_con_vad`` (mismo mecanismo que el uso
    real, no una toma continua aparte — ver docstring del módulo) y guarda
    el PROMEDIO de sus embeddings como referencia: una sola frase puede
    salir atípica (ruido, carraspera); promediar varias da una huella más
    representativa de la voz real de la persona."""
    verificador = VerificadorHablante(umbral=config.umbral_voz_dueño)
    embeddings = []
    for i in range(N_FRASES_ENROLAMIENTO):
        anunciar(f"⏺  Decí algo ahora (frase {i + 1} de {N_FRASES_ENROLAMIENTO})...")
        audio = _grabar_frase_con_limite(config.sensibilidad_voz)
        embeddings.append(verificador.embedding(audio))

    embedding_promedio = np.mean(embeddings, axis=0)
    ruta = ruta_referencia(config.carpeta_datos)
    guardar_referencia(ruta, embedding_promedio)
    anunciar(f"Listo: voz de referencia guardada en {ruta}.")
    return ruta


LIMITE_SEGUNDOS_POR_FRASE = 20


def _grabar_frase_con_limite(sensibilidad: float, limite_segundos: float = LIMITE_SEGUNDOS_POR_FRASE):
    """Como ``grabar_frase_con_vad``, pero con un límite de tiempo: esa
    función espera voz SIN límite (correcto para ``Oido`` en uso normal,
    que debe seguir escuchando indefinidamente) — mal en el enrolamiento,
    donde si el micrófono está mudo o nadie habla, colgaría el arranque de
    Jarvis para siempre en vez de fallar con un error claro. Corre la
    grabación real en un hilo aparte y espera con timeout."""
    import queue
    import threading

    from .oido import grabar_frase_con_vad

    resultado: queue.Queue = queue.Queue(maxsize=1)

    def trabajo() -> None:
        try:
            resultado.put(("ok", grabar_frase_con_vad(sensibilidad=sensibilidad)))
        except Exception as error:  # noqa: BLE001 — se re-lanza tal cual del lado del que espera
            resultado.put(("error", error))

    threading.Thread(target=trabajo, daemon=True).start()
    try:
        estado, valor = resultado.get(timeout=limite_segundos)
    except queue.Empty as error:
        raise RuntimeError(
            f"No se detectó tu voz en {limite_segundos}s. ¿Está el micrófono conectado y sin mutear?"
        ) from error
    if estado == "error":
        raise valor
    return valor
