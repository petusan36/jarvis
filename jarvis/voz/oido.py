"""Escucha por el micrófono y transcribe con Whisper (faster-whisper, local).

Por defecto escucha de forma continua: detecta cuándo empiezas a hablar por el
volumen (comparado con el ruido de fondo, que mide sola) y corta tras un breve
silencio. Mientras Jarvis habla, el micrófono principal está cerrado (así no
se escucha a sí mismo) — pero si el motor de voz lo permite, un "vigía" aparte
(`vigilar_interrupcion`) escucha en paralelo solo la palabra de corte, sin eco
cancelado: con parlantes puede, en teoría, confundir su propia voz, aunque es
poco probable salvo que la respuesta contenga la palabra "Jarvis". Con
`pulsar=True` vuelve al modo antiguo de pulsar Enter.
"""

from __future__ import annotations

import collections
import queue
import re
import threading
import time

from ..hud import HudNulo

FRECUENCIA = 16000  # Whisper trabaja a 16 kHz mono
BLOQUE = 480  # 30 ms por bloque de audio

# Frases que Whisper "oye" a veces en el ruido o el silencio (alucinaciones típicas).
ALUCINACIONES = {
    "gracias", "gracias por ver", "gracias por ver el video", "gracias por ver el vídeo",
    "subtítulos realizados por la comunidad de amaraorg", "subtítulos por la comunidad de amaraorg",
    "suscríbete", "suscribete", "thank you", "thanks for watching", "you", "",
}


class DetectorVoz:
    """Decide, bloque a bloque, cuándo empieza y cuándo termina una frase.

    Recibe el volumen (RMS) de cada bloque de 30 ms y devuelve "inicio", "fin" o None.
    El umbral se adapta al ruido de fondo de la habitación.
    """

    def __init__(self, sensibilidad: float = 3.0, umbral_minimo: float = 0.006,
                 bloques_inicio: int = 4, bloques_silencio: int = 27, bloques_maximo: int = 1000):
        self.sensibilidad = sensibilidad  # cuántas veces por encima del ruido cuenta como voz
        self.umbral_minimo = umbral_minimo
        self.bloques_inicio = bloques_inicio  # ~120 ms seguidos de voz para empezar
        self.bloques_silencio = bloques_silencio  # ~0,8 s de silencio para terminar
        self.bloques_maximo = bloques_maximo  # ~30 s como mucho por frase
        self.ruido = umbral_minimo / sensibilidad
        self.hablando = False
        self._seguidos = 0
        self._silencio = 0
        self._duracion = 0

    @property
    def umbral(self) -> float:
        return max(self.umbral_minimo, self.ruido * self.sensibilidad)

    def procesar(self, rms: float) -> str | None:
        es_voz = rms > self.umbral
        if not self.hablando:
            if es_voz:
                self._seguidos += 1
                if self._seguidos >= self.bloques_inicio:
                    self.hablando = True
                    self._silencio = 0
                    self._duracion = self._seguidos
                    return "inicio"
            else:
                self._seguidos = 0
                # El ruido de fondo se aprende solo cuando nadie habla.
                self.ruido = 0.95 * self.ruido + 0.05 * rms
            return None

        self._duracion += 1
        self._silencio = 0 if es_voz else self._silencio + 1
        if self._silencio >= self.bloques_silencio or self._duracion >= self.bloques_maximo:
            self.hablando = False
            self._seguidos = 0
            return "fin"
        return None


class Oido:
    def __init__(self, modelo: str = "small", idioma: str = "es", hud: HudNulo | None = None,
                 pulsar: bool = False, palabra_activacion: str = "", sensibilidad: float = 3.0,
                 verificador=None, referencia_voz=None):
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError(
                "Falta el soporte de voz. Instálalo con: pip install -e ."
            ) from error
        self.idioma = idioma
        self.hud = hud or HudNulo()
        self.pulsar = pulsar
        # Admite variantes separadas por comas, p. ej. "jarvis,yarvis", por si Whisper la escribe distinto.
        self.palabra_activacion = palabra_activacion.strip()
        self.sensibilidad = sensibilidad
        self._avisado = False
        # La primera vez descarga el modelo (small ≈ 500 MB).
        self.modelo = WhisperModel(modelo, device="auto", compute_type="int8")
        # Reconocimiento de hablante (ver jarvis.voz.hablante). Si no hay
        # verificador configurado o todavía no hay voz de referencia
        # enrolada, es_dueño queda siempre en True: Jarvis no exige nada
        # hasta que el usuario enrola su voz.
        self.verificador = verificador
        self.referencia_voz = referencia_voz
        # Lo deja escrito escuchar() después de cada frase, para que quien
        # llame (ver jarvis.__main__) sepa si la voz coincidió con la dueña.
        self.es_dueño = True

    def escuchar(self) -> str:
        """Espera a que el usuario diga algo y devuelve el texto transcrito."""
        while True:
            audio = self._grabar_pulsando() if self.pulsar else self._grabar_continuo()
            self.hud.estado("pensando")
            texto = self._transcribir(audio) if audio is not None else ""
            self.es_dueño = self._coincide_con_dueño(audio) if audio is not None else True
            if self.pulsar:
                return texto
            texto = filtrar_palabra_activacion(texto, self.palabra_activacion)
            if texto:
                return texto
            # Ruido, una alucinación de Whisper o no iba dirigido a Jarvis: seguir escuchando.

    def _coincide_con_dueño(self, audio) -> bool:
        if self.verificador is None or self.referencia_voz is None:
            return True
        try:
            return self.verificador.coincide(audio, self.referencia_voz)
        except Exception:
            return True  # el reconocimiento de hablante es un extra: si falla, no bloquea a Jarvis

    def vigilar_interrupcion(self, palabra: str, detener_vigia: threading.Event,
                             al_detectar) -> threading.Event:
        """Escucha en paralelo mientras Jarvis habla. Si oye `palabra`, llama a
        `al_detectar()` de inmediato (desde este mismo hilo, para no esperar a
        que el principal quede libre — está bloqueado en habla.decir()) y
        activa el evento que devuelve. Deja de escuchar en cuanto
        `detener_vigia` se active (Jarvis terminó solo, sin que lo corten) —
        así no quedan dos micrófonos abiertos a la vez."""
        interrumpido = threading.Event()

        def _vigilar() -> None:
            import numpy as np
            import sounddevice as sd

            bloques: queue.Queue = queue.Queue()

            def al_recibir(datos, _frames, _tiempo, _estado):
                bloques.put(datos[:, 0].copy())

            detector = DetectorVoz(sensibilidad=self.sensibilidad)
            frase: list = []
            try:
                with sd.InputStream(samplerate=FRECUENCIA, channels=1, dtype="float32",
                                    blocksize=BLOQUE, callback=al_recibir):
                    while not detener_vigia.is_set():
                        try:
                            bloque = bloques.get(timeout=0.2)
                        except queue.Empty:
                            continue
                        rms = float(np.sqrt(np.mean(bloque ** 2)))
                        evento = detector.procesar(rms)
                        if not (detector.hablando or evento == "fin"):
                            continue
                        frase.append(bloque)
                        if evento != "fin":
                            continue
                        texto = self._transcribir(np.concatenate(frase))
                        frase = []
                        if filtrar_palabra_activacion(texto, palabra):
                            al_detectar()
                            interrumpido.set()
                            return
            except Exception:
                pass  # el vigía es un extra: si falla, Jarvis sigue hablando normal

        threading.Thread(target=_vigilar, daemon=True).start()
        return interrumpido

    def _grabar_continuo(self):
        """Graba la siguiente frase: empieza cuando oye voz y corta tras un silencio."""
        import numpy as np
        import sounddevice as sd

        if not self._avisado:
            aviso = (f"di «{self.palabra_activacion.split(',')[0].strip()}» y lo que necesites"
                     if self.palabra_activacion else "habla cuando quieras")
            print(f"🎙  Te escucho: {aviso}. Ctrl+C para salir.")
            self._avisado = True

        bloques: queue.Queue = queue.Queue()

        def al_recibir(datos, _frames, _tiempo, _estado):
            bloques.put(datos[:, 0].copy())

        detector = DetectorVoz(sensibilidad=self.sensibilidad)
        previo = collections.deque(maxlen=10)  # 300 ms antes de detectar voz, para no comerse el inicio
        frase: list = []
        self.hud.estado("reposo")
        with sd.InputStream(samplerate=FRECUENCIA, channels=1, dtype="float32",
                            blocksize=BLOQUE, callback=al_recibir):
            # Al abrir el micrófono justo después de que Jarvis hable puede quedar eco: se descarta.
            fin_eco = time.monotonic() + 0.25
            while True:
                bloque = bloques.get()
                if time.monotonic() < fin_eco:
                    continue
                rms = float(np.sqrt(np.mean(bloque ** 2)))
                evento = detector.procesar(rms)
                if detector.hablando or evento == "fin":
                    frase.append(bloque)
                    self.hud.nivel(rms * 8)  # el habla normal ronda 0,02-0,15
                    if evento == "inicio":
                        frase[:0] = list(previo)
                        self.hud.estado("escuchando", "")
                    elif evento == "fin":
                        break
                else:
                    previo.append(bloque)
        self.hud.nivel(0)
        return np.concatenate(frase)

    def _grabar_pulsando(self):
        """Modo clásico: Enter para empezar y Enter para terminar."""
        import numpy as np
        import sounddevice as sd

        self.hud.estado("reposo")
        input("🎙  Pulsa Enter y habla...")
        trozos: queue.Queue = queue.Queue()

        def al_recibir(datos, _frames, _tiempo, _estado):
            trozos.put(datos.copy())
            self.hud.nivel(float(np.sqrt(np.mean(datos ** 2))) * 8)

        self.hud.estado("escuchando", "")
        with sd.InputStream(samplerate=FRECUENCIA, channels=1, dtype="float32", callback=al_recibir):
            input("⏺  Grabando... pulsa Enter para terminar.")
        if trozos.empty():
            return None
        return np.concatenate(list(trozos.queue)).flatten()

    def _transcribir(self, audio) -> str:
        segmentos, _info = self.modelo.transcribe(audio, language=self.idioma, vad_filter=True)
        texto = " ".join(s.text.strip() for s in segmentos).strip()
        return "" if _normalizar(texto) in ALUCINACIONES else texto


def filtrar_palabra_activacion(texto: str, palabra: str) -> str:
    """Si hay palabra de activación, solo deja pasar frases que la contienen (y la quita)."""
    variantes = [re.escape(p.strip()) for p in palabra.split(",") if p.strip()]
    if not variantes:
        return texto
    coincidencia = re.search(rf"\b(?:{'|'.join(variantes)})\b[\s,.:;!?¡¿]*", texto, re.IGNORECASE)
    if not coincidencia:
        return ""
    resto = (texto[:coincidencia.start()] + texto[coincidencia.end():]).strip(" ,.;:!?¡¿")
    # Solo "Jarvis": se trata como un saludo para que conteste.
    return resto or texto.strip()


def _normalizar(texto: str) -> str:
    return re.sub(r"[^\w\s]", "", texto.lower()).strip()
