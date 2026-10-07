"""Configuración leída de variables de entorno (y de un archivo .env si existe)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Mismo directorio que ``Config.carpeta_datos`` (no se puede importar la
# dataclass todavía: su propio default se resuelve leyendo este .env). NO
# usar una ruta relativa como ".env": depende del directorio de trabajo, que
# para un proceso arrancado por doble clic en el ícono de escritorio NO es
# el repo (en macOS suele ser "/", de solo lectura) — eso rompía el guardado
# con "[Errno 30] Read-only file system: '.env'".
_RUTA_ENV_POR_DEFECTO = Path.home() / ".jarvis" / ".env"


def _cargar_dotenv(ruta: Path | None = None) -> None:
    """Carga un .env sencillo (CLAVE=valor) sin pisar variables ya definidas.

    Si no se pasa ``ruta`` explícita, mira dos lugares, en orden (el primero
    que defina una clave gana, por ``setdefault``): el ``.env`` del propio
    repo (ruta relativa, para quien corre `python -m jarvis` desde una
    terminal con el repo como directorio de trabajo — convención de
    desarrollo, ver README) y ``~/.jarvis/.env`` (donde el menú de conexión
    guarda la elección — el único lugar que funciona también cuando Jarvis
    arranca desde el ícono de escritorio, sin ese directorio de trabajo)."""
    rutas = [ruta] if ruta is not None else [Path(".env"), _RUTA_ENV_POR_DEFECTO]
    for candidata in rutas:
        if not candidata.is_file():
            continue
        for linea in candidata.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def guardar_en_env(clave: str, valor: str, ruta: Path | None = None) -> None:
    """Escribe o reemplaza CLAVE=valor en .env, conservando el resto del
    archivo y con permisos 0600 (solo el usuario puede leerlo).

    Se usa desde el menú de configuración de IA (``jarvis.__main__``) para
    persistir el proveedor elegido, el modelo y la clave de API, de modo que
    no haya que repetir la elección en cada arranque. No imprime ni registra
    el valor guardado.

    Por defecto (``ruta=None``) escribe siempre en ``~/.jarvis/.env``, nunca
    en el directorio de trabajo: se resuelve en el cuerpo de la función (no
    como valor por defecto del parámetro) para que un test pueda
    monkeypatchear ``_RUTA_ENV_POR_DEFECTO`` y que surta efecto — un default
    de parámetro queda fijo en el momento en que se define la función.

    Rechaza un salto de línea en ``clave`` o ``valor``: el formato de .env es
    una línea CLAVE=valor por entrada, así que un salto de línea en el valor
    inyectaría líneas nuevas — pisando cualquier otra variable, incluida
    ANTHROPIC_API_KEY — en vez de quedar contenido en esta. Defensa en
    profundidad: quien llama (p. ej. la herramienta "guardar_nombre", con un
    valor que en última instancia decide el modelo) debería validar esto
    también, pero esta función no confía en que lo haya hecho."""
    if "\n" in clave or "\r" in clave or "\n" in valor or "\r" in valor:
        raise ValueError("clave o valor con salto de línea: no se puede guardar en .env")
    if ruta is None:
        ruta = _RUTA_ENV_POR_DEFECTO
    ruta.parent.mkdir(parents=True, exist_ok=True)
    lineas = ruta.read_text(encoding="utf-8").splitlines() if ruta.is_file() else []
    nueva = f"{clave}={valor}"
    for i, linea in enumerate(lineas):
        if linea.strip().startswith(f"{clave}="):
            lineas[i] = nueva
            break
    else:
        lineas.append(nueva)
    contenido = "\n".join(lineas) + "\n"
    if ruta.is_file():
        os.chmod(ruta, 0o600)  # ya existía con permisos más abiertos: cerrarlos antes de escribir
    descriptor = os.open(str(ruta), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
        archivo.write(contenido)


@dataclass
class Config:
    motor: str = "auto"  # api | suscripcion | codex | auto
    # api: proveedor-con-clave (ver `proveedor`); suscripcion: Claude Code (Agent SDK);
    # codex: sesión de Codex CLI (endpoint interno de ChatGPT, sin clave); auto: detecta
    # entre las tres según qué haya configurado/disponible.
    proveedor: str = "anthropic"  # anthropic | ollama (solo aplica con motor=api)
    modelo: str = "claude-opus-5-5"
    ollama_url: str = "http://localhost:11434"  # base de la API local, si proveedor=ollama
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
    memoria_habilitada: bool = False  # memoria permanente (ver jarvis.memoria); requiere ollama + nomic-embed-text
    memoria_modelo_llm: str = "qwen3:8b"  # modelo de Ollama para extracción de entidades (graphiti)
    memoria_modelo_embedding: str = "nomic-embed-text"
    memoria_ventana_gracia_dias: int = 180  # cuánto tardan los hechos invalidados en archivarse en frío
    # Reconocimiento de hablante (ver jarvis.voz.hablante): mientras no haya
    # voz enrolada (--enrolar-voz), no exige nada, igual que siempre.
    reconocimiento_voz_habilitado: bool = True
    umbral_voz_dueño: float = 0.75
    # Modo de escucha pasiva (ver jarvis.voz.oido.Oido.dormir): tras este
    # tiempo sin una frase real dirigida a Jarvis, entra solo en reposo y
    # solo vuelve a atender si lo nombrás. 0 desactiva el reposo automático
    # (el pedido explícito con la herramienta "dormir_jarvis" sigue andando).
    segundos_reposo_inactividad: float = 300.0

    @classmethod
    def desde_entorno(cls) -> "Config":
        _cargar_dotenv()
        base = cls()
        return cls(
            motor=os.getenv("JARVIS_MOTOR", base.motor).lower(),
            proveedor=os.getenv("JARVIS_PROVEEDOR", base.proveedor).lower(),
            modelo=os.getenv("JARVIS_MODELO", base.modelo),
            ollama_url=os.getenv("JARVIS_OLLAMA_URL", base.ollama_url),
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
            memoria_habilitada=os.getenv("JARVIS_MEMORIA", "1" if base.memoria_habilitada else "0").lower()
            in ("1", "true", "si", "sí"),
            memoria_modelo_llm=os.getenv("JARVIS_MEMORIA_MODELO_LLM", base.memoria_modelo_llm),
            memoria_modelo_embedding=os.getenv("JARVIS_MEMORIA_MODELO_EMBEDDING", base.memoria_modelo_embedding),
            memoria_ventana_gracia_dias=int(
                os.getenv("JARVIS_MEMORIA_VENTANA_GRACIA_DIAS", base.memoria_ventana_gracia_dias)
            ),
            reconocimiento_voz_habilitado=os.getenv(
                "JARVIS_VOZ_RECONOCIMIENTO", "1" if base.reconocimiento_voz_habilitado else "0"
            ).lower() in ("1", "true", "si", "sí"),
            umbral_voz_dueño=float(os.getenv("JARVIS_VOZ_UMBRAL", base.umbral_voz_dueño)),
            segundos_reposo_inactividad=float(
                os.getenv("JARVIS_REPOSO_INACTIVIDAD_SEGUNDOS", base.segundos_reposo_inactividad)
            ),
        )
