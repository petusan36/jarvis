"""Convierte texto en voz con varios motores, del más natural al más básico.

- elevenlabs: voz neuronal en la nube (de pago, la más natural). Necesita ELEVENLABS_API_KEY.
- kokoro: voz neuronal local y gratuita (pip install -e '.[voz-kokoro]'), mejor calidad que Piper.
  Necesita espeak-ng instalado en el sistema para el español.
- piper: voz neuronal local y gratuita (pip install piper-tts). Descarga la voz la primera vez.
- macos: el comando `say` de macOS, con las voces mejoradas o premium del sistema.
- pyttsx3: las voces básicas del sistema (Linux y Windows).

Si un motor falla a mitad de la conversación, Jarvis sigue hablando con el siguiente
en lugar de quedarse mudo.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

MOTORES = ("elevenlabs", "kokoro", "piper", "macos", "pyttsx3")

# Voz de Piper por defecto: hombre, español de España, tono sereno.
VOZ_PIPER = "es_ES-davefx-medium"
# Voz de Kokoro por defecto: "Alex", voz masculina en español (modelo abierto Apache-2.0,
# no imita a ningún actor). Alternativa: "em_santa".
VOZ_KOKORO = "em_alex"
# Idioma de config.idioma -> código de idioma de Kokoro.
IDIOMAS_KOKORO = {"es": "e", "en": "a", "fr": "f", "it": "i", "pt": "p", "hi": "h", "ja": "j", "zh": "z"}
# Voz de ElevenLabs por defecto: "George", voz masculina británica, cálida y madura
# (de la biblioteca de ElevenLabs; no imita a ningún actor). Habla español con el modelo multilingüe.
VOZ_ELEVENLABS = "JBFqnCBsd6RMkjVDRZzb"
MODELO_ELEVENLABS = "eleven_multilingual_v2"
# Voces de macOS preferidas para español, de más natural a menos.
VOCES_MACOS = ("Jorge", "Juan", "Diego", "Carlos")
VELOCIDAD_NORMAL = 170  # palabras por minuto de referencia


class NoInstalado(RuntimeError):
    """El motor necesita un paquete que no está instalado."""


class Habla:
    """Usa el primer motor que funcione y pasa al siguiente si uno falla."""

    def __init__(self, motores: list):
        if not motores:
            raise RuntimeError(
                "No hay ningún motor de voz disponible. Instala uno con: pip install -e '.[voz]'"
            )
        self.motores = list(motores)

    @property
    def nombre(self) -> str:
        return self.motores[0].nombre

    def decir(self, texto: str) -> None:
        texto = _limpiar(texto)
        if not texto:
            return
        while self.motores:
            motor = self.motores[0]
            try:
                motor.decir(texto)
                return
            except Exception as error:  # cualquier fallo del motor: no dejar a Jarvis mudo
                self.motores.pop(0)
                siguiente = self.motores[0].nombre if self.motores else None
                print(f"(la voz {motor.nombre} ha fallado: {error}"
                      + (f"; sigo con {siguiente})" if siguiente else ")"), file=sys.stderr)
        # Sin motores: la respuesta ya se ha mostrado por texto.


def crear_habla(config) -> Habla:
    """Monta la lista de motores según JARVIS_VOZ_MOTOR (auto = el mejor disponible)."""
    pedido = config.motor_voz
    if pedido != "auto" and pedido not in MOTORES:
        raise RuntimeError(f"JARVIS_VOZ_MOTOR no válido: {pedido} (usa {', '.join(('auto',) + MOTORES)})")
    orden = [m for m in MOTORES if m != pedido]
    if pedido != "auto":
        orden.insert(0, pedido)

    motores, avisos = [], []
    for nombre in orden:
        try:
            motor = _crear_motor(nombre, config, explicito=nombre == pedido)
        except NoInstalado as error:
            if nombre == pedido:
                avisos.append(str(error))
            continue
        except RuntimeError as error:
            avisos.append(f"{nombre}: {error}")
            continue
        if motor is not None:
            motores.append(motor)
    for aviso in avisos:
        print(f"(voz: {aviso})", file=sys.stderr)
    return Habla(motores)


def _crear_motor(nombre: str, config, explicito: bool):
    voz = config.voz if explicito or config.motor_voz == "auto" else ""
    if nombre == "elevenlabs":
        if not config.elevenlabs_api_key:
            if explicito:
                raise RuntimeError("falta ELEVENLABS_API_KEY en el .env")
            return None
        return MotorElevenLabs(config.elevenlabs_api_key, config.elevenlabs_voz or VOZ_ELEVENLABS,
                               config.elevenlabs_modelo or MODELO_ELEVENLABS, config.velocidad_voz)
    if nombre == "kokoro":
        return MotorKokoro(voz or VOZ_KOKORO, config.velocidad_voz, config.idioma)
    if nombre == "piper":
        return MotorPiper(config.carpeta_datos / "voces", _voz_de(voz, "piper"), config.velocidad_voz)
    if nombre == "macos":
        if sys.platform != "darwin" or not shutil.which("say"):
            return None
        return MotorMacos(_voz_de(voz, "macos"), config.velocidad_voz, config.idioma)
    if nombre == "pyttsx3":
        if sys.platform == "darwin" and not explicito:
            return None  # en macOS pyttsx3 se cuelga tras unas frases: mejor `say`
        return MotorPyttsx3(config.idioma, config.velocidad_voz)
    return None


def _voz_de(voz: str, motor: str) -> str:
    """JARVIS_VOZ solo se aplica al motor al que corresponde."""
    if not voz:
        return ""
    es_piper = voz.endswith(".onnx") or bool(re.match(r"^[a-z]{2}_[A-Z]{2}-", voz))
    return voz if es_piper == (motor == "piper") else ""


class MotorElevenLabs:
    nombre = "elevenlabs"
    frecuencia = 22050

    def __init__(self, clave: str, voz: str, modelo: str, velocidad: int):
        self.clave, self.voz, self.modelo = clave, voz, modelo
        self.velocidad = max(0.7, min(1.2, velocidad / VELOCIDAD_NORMAL))
        self.sd, self.np = _audio()

    def decir(self, texto: str) -> None:
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/{self.voz}"
               f"?output_format=pcm_{self.frecuencia}")
        cuerpo = json.dumps({
            "text": texto,
            "model_id": self.modelo,
            "voice_settings": {"stability": 0.6, "similarity_boost": 0.8, "speed": self.velocidad},
        }).encode()
        peticion = urllib.request.Request(url, data=cuerpo, method="POST", headers={
            "xi-api-key": self.clave, "Content-Type": "application/json", "Accept": "audio/pcm",
        })
        try:
            with urllib.request.urlopen(peticion, timeout=30) as respuesta:
                pcm = respuesta.read()
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"ElevenLabs respondió {error.code}") from error
        muestras = self.np.frombuffer(pcm, dtype=self.np.int16)
        self.sd.play(muestras, self.frecuencia)
        self.sd.wait()


class MotorKokoro:
    """Kokoro-82M: voz neuronal local, gratuita, mejor calidad que Piper (Apache-2.0)."""

    nombre = "kokoro"
    frecuencia = 24000

    def __init__(self, voz: str, velocidad: int, idioma: str):
        try:
            from kokoro import KPipeline
        except ImportError as error:
            raise NoInstalado(
                "Kokoro no está instalado: pip install -e '.[voz-kokoro]' (necesita espeak-ng)"
            ) from error
        self.sd, self.np = _audio()
        self.voz = voz
        self.velocidad = velocidad / VELOCIDAD_NORMAL
        self.pipeline = KPipeline(lang_code=IDIOMAS_KOKORO.get(idioma[:2].lower(), "e"))

    def decir(self, texto: str) -> None:
        trozos = [audio for _, _, audio in self.pipeline(texto, voice=self.voz, speed=self.velocidad)]
        if not trozos:
            return
        self.sd.play(self.np.concatenate(trozos), self.frecuencia)
        self.sd.wait()


class MotorPiper:
    nombre = "piper"

    def __init__(self, carpeta: Path, voz: str, velocidad: int):
        try:
            from piper import PiperVoice
            from piper.config import SynthesisConfig
        except ImportError as error:
            raise NoInstalado("Piper no está instalado: pip install -e '.[voz-natural]'") from error
        self.sd, self.np = _audio()
        modelo = _modelo_piper(carpeta, voz or VOZ_PIPER)
        self.voz = PiperVoice.load(modelo)
        self.ajustes = SynthesisConfig(length_scale=VELOCIDAD_NORMAL / max(velocidad, 60))

    def decir(self, texto: str) -> None:
        trozos = [t.audio_float_array for t in self.voz.synthesize(texto, syn_config=self.ajustes)]
        if not trozos:
            return
        self.sd.play(self.np.concatenate(trozos), self.voz.config.sample_rate)
        self.sd.wait()


def _modelo_piper(carpeta: Path, voz: str) -> Path:
    """Devuelve el .onnx de la voz, descargándola la primera vez (unos 60 MB)."""
    if voz.endswith(".onnx"):
        ruta = Path(voz).expanduser()
        if not ruta.is_file():
            raise RuntimeError(f"no encuentro la voz de Piper {ruta}")
        return ruta
    ruta = carpeta / f"{voz}.onnx"
    if not ruta.is_file():
        from piper.download_voices import download_voice
        carpeta.mkdir(parents=True, exist_ok=True)
        print(f"(descargando la voz {voz} de Piper, solo la primera vez...)", file=sys.stderr)
        try:
            download_voice(voz, carpeta)
        except Exception as error:
            raise RuntimeError(f"no he podido descargar la voz {voz}: {error}") from error
    return ruta


class MotorMacos:
    """Usa `say` en un proceso aparte: no se cuelga como pyttsx3 en macOS."""

    nombre = "macos"

    def __init__(self, voz: str, velocidad: int, idioma: str):
        self.velocidad = velocidad
        self.voz = voz or elegir_voz_macos(_voces_macos(), idioma)

    def decir(self, texto: str) -> None:
        orden = ["say", "-r", str(self.velocidad)]
        if self.voz:
            orden += ["-v", self.voz]
        resultado = subprocess.run(orden + ["--", texto], capture_output=True, text=True)
        if resultado.returncode != 0:
            raise RuntimeError(resultado.stderr.strip() or f"say terminó con código {resultado.returncode}")


def _voces_macos() -> list[tuple[str, str]]:
    try:
        salida = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return analizar_voces_macos(salida)


def analizar_voces_macos(salida: str) -> list[tuple[str, str]]:
    """Convierte la salida de `say -v ?` en [(nombre, idioma)]."""
    voces = []
    for linea in salida.splitlines():
        m = re.match(r"^(.+?)\s+([a-z]{2,3}[_-][A-Za-z0-9]+)\s+#", linea)
        if m:
            voces.append((m.group(1).strip(), m.group(2)))
    return voces


def elegir_voz_macos(voces: list[tuple[str, str]], idioma: str) -> str:
    """Prefiere una voz masculina conocida y, de ella, la versión premium o mejorada."""
    del_idioma = [(n, i) for n, i in voces if i.lower().startswith(idioma.lower())]
    if not del_idioma:
        return ""

    def calidad(nombre: str) -> int:
        n = nombre.lower()
        if "premium" in n or "prémium" in n:
            return 0
        if "enhanced" in n or "mejorada" in n:
            return 1
        return 2

    for preferida in VOCES_MACOS:
        candidatas = [n for n, _ in del_idioma if n.split(" (")[0] == preferida]
        if candidatas:
            return min(candidatas, key=calidad)
    return min((n for n, _ in del_idioma), key=calidad)


class MotorPyttsx3:
    nombre = "pyttsx3"

    def __init__(self, idioma: str, velocidad: int):
        try:
            import pyttsx3
        except ImportError as error:
            raise NoInstalado("Falta pyttsx3: pip install -e '.[voz]'") from error
        self.motor = pyttsx3.init()
        self.motor.setProperty("rate", velocidad)
        voz = _buscar_voz(self.motor.getProperty("voices"), idioma)
        if voz is not None:
            self.motor.setProperty("voice", voz.id)

    def decir(self, texto: str) -> None:
        self.motor.say(texto)
        self.motor.runAndWait()
        self.motor.stop()


def _buscar_voz(voces, idioma: str):
    """Elige la primera voz del sistema que hable el idioma pedido."""
    for voz in voces:
        idiomas = [i.decode(errors="ignore") if isinstance(i, bytes) else str(i)
                   for i in (getattr(voz, "languages", None) or [])]
        nombre = f"{voz.id} {voz.name}".lower()
        if any(idioma in i.lower() for i in idiomas) or "spanish" in nombre or f"{idioma}_" in nombre:
            return voz
    return None


def _audio():
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as error:
        raise NoInstalado("Faltan sounddevice y numpy: pip install -e '.[voz]'") from error
    return sd, np


def _limpiar(texto: str) -> str:
    """Quita el formato Markdown para que no lea asteriscos ni almohadillas."""
    texto = re.sub(r"```.*?```", " ", texto, flags=re.S)
    texto = re.sub(r"[*_#`>]+", "", texto)
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    return re.sub(r"\s+", " ", texto).strip()
