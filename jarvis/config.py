"""Configuración leída de variables de entorno (y de un archivo .env si existe)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _cargar_dotenv(ruta: Path = Path(".env")) -> None:
    """Carga un .env sencillo (CLAVE=valor) sin pisar variables ya definidas."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


@dataclass
class Config:
    motor: str = "auto"  # api | suscripcion | auto (API si hay clave, si no la suscripción)
    modelo: str = "claude-opus-5-5"
    esfuerzo: str = "low"  # low | medium | high: "low" responde más rápido, ideal para voz
    max_tokens: int = 16000
    nombre_usuario: str = "señor"
    carpeta_datos: Path = field(default_factory=lambda: Path.home() / ".jarvis")
    modelo_whisper: str = "small"
    idioma: str = "es"
    puerto_hud: int = 8765
    palabra_activacion: str = ""  # vacío = responde a todo lo que oiga; "jarvis" = solo si le llamas
    sensibilidad_voz: float = 3.0  # más bajo = detecta voz más baja (y más ruido)
    motor_voz: str = "auto"  # auto | elevenlabs | kokoro | piper | macos | pyttsx3
    voz: str = ""  # nombre de la voz (p. ej. "Jorge (Premium)" en macOS, "em_alex" en Kokoro o "es_ES-davefx-medium" en Piper)
    velocidad_voz: int = 165  # palabras por minuto
    elevenlabs_api_key: str = ""
    elevenlabs_voz: str = ""
    elevenlabs_modelo: str = ""
    youtube_api_key: str = ""  # opcional: sin ella, "reproducir música" abre los resultados y elige el usuario

    @classmethod
    def desde_entorno(cls) -> "Config":
        _cargar_dotenv()
        base = cls()
        return cls(
            motor=os.getenv("JARVIS_MOTOR", base.motor).lower(),
            modelo=os.getenv("JARVIS_MODELO", base.modelo),
            esfuerzo=os.getenv("JARVIS_ESFUERZO", base.esfuerzo),
            max_tokens=int(os.getenv("JARVIS_MAX_TOKENS", base.max_tokens)),
            nombre_usuario=os.getenv("JARVIS_NOMBRE_USUARIO", base.nombre_usuario),
            carpeta_datos=Path(os.getenv("JARVIS_CARPETA_DATOS", base.carpeta_datos)).expanduser(),
            modelo_whisper=os.getenv("JARVIS_MODELO_WHISPER", base.modelo_whisper),
            idioma=os.getenv("JARVIS_IDIOMA", base.idioma),
            puerto_hud=int(os.getenv("JARVIS_PUERTO_HUD", base.puerto_hud)),
            palabra_activacion=os.getenv("JARVIS_PALABRA_ACTIVACION", base.palabra_activacion),
            sensibilidad_voz=float(os.getenv("JARVIS_SENSIBILIDAD_VOZ", base.sensibilidad_voz)),
            motor_voz=os.getenv("JARVIS_VOZ_MOTOR", base.motor_voz).lower(),
            voz=os.getenv("JARVIS_VOZ", base.voz),
            velocidad_voz=int(os.getenv("JARVIS_VOZ_VELOCIDAD", base.velocidad_voz)),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", base.elevenlabs_api_key),
            elevenlabs_voz=os.getenv("JARVIS_ELEVENLABS_VOZ", base.elevenlabs_voz),
            elevenlabs_modelo=os.getenv("JARVIS_ELEVENLABS_MODELO", base.elevenlabs_modelo),
            youtube_api_key=os.getenv("YOUTUBE_API_KEY", base.youtube_api_key),
        )
