"""Punto de entrada: python -m jarvis [--texto] [--sin-hud] [--silencio] [--pulsar] [--hud] [--instalar-app].

Por defecto arranca el modo completo: te escucha, te responde hablando y abre
la animación HUD. Usa --texto para el modo clásico de escribir y leer.
--instalar-app crea un ícono de escritorio y termina sin arrancar Jarvis.
"""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

import anthropic

from .cerebro import Cerebro
from .config import Config
from .herramientas import Herramientas
from .hud import Hud, HudNulo

SALIR = {"salir", "adiós", "adios", "exit", "quit"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis", description="Asistente personal tipo Jarvis.")
    parser.add_argument("--texto", action="store_true",
                        help="Modo texto clásico: escribes y lees, sin voz ni HUD (por defecto: modo completo).")
    parser.add_argument("--sin-hud", action="store_true",
                        help="En modo completo (voz), no abrir la animación HUD.")
    parser.add_argument("--silencio", action="store_true",
                        help="En modo voz, responder solo por texto (sin síntesis).")
    parser.add_argument("--pulsar", action="store_true",
                        help="En modo voz, pulsar Enter para hablar en lugar de escuchar siempre.")
    parser.add_argument("--hud", action="store_true",
                        help="Con --texto, abre igual la animación HUD aunque no haya voz.")
    parser.add_argument("--instalar-app", action="store_true",
                        help="Crea un ícono de escritorio para esta instalación y termina.")
    args = parser.parse_args(argv)

    if args.instalar_app:
        from .escritorio import instalar_app_escritorio
        print(f"Listo: {instalar_app_escritorio()}")
        return 0

    config = Config.desde_entorno()
    clave_persistente = "ANTHROPIC_API_KEY" in os.environ  # ya venía de .env/entorno real
    try:
        cerebro = _crear_cerebro(config)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    try:
        return _ejecutar(args, config, cerebro)
    finally:
        if not clave_persistente:
            os.environ.pop("ANTHROPIC_API_KEY", None)  # la del menú no sobrevive a esta ejecución


def _ejecutar(args, config: Config, cerebro) -> int:
    modo_voz = not args.texto
    usar_hud = (modo_voz and not args.sin_hud) or (not modo_voz and args.hud)

    hud = HudNulo()
    if usar_hud:
        hud = Hud(config.puerto_hud)
        print(f"HUD en {hud.url}")

    oido = habla = None
    if modo_voz:
        from .voz.oido import Oido
        oido = Oido(config.modelo_whisper, config.idioma, hud, pulsar=args.pulsar,
                    palabra_activacion=config.palabra_activacion,
                    sensibilidad=config.sensibilidad_voz)
        if not args.silencio:
            from .voz.habla import crear_habla
            try:
                habla = crear_habla(config)
            except RuntimeError as error:
                print(error, file=sys.stderr)
                return 1
            print(f"(voz: {habla.nombre})")

    saludo = (f"A su servicio, {config.nombre_usuario}. "
              f"{'Diga' if oido else 'Escriba'} 'salir' para terminar.")
    _decir(saludo, habla, hud)

    while True:
        try:
            if not oido:
                hud.estado("escuchando")
            texto = oido.escuchar() if oido else input("Tú: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        texto = texto.strip()
        if not texto:
            continue
        if oido:
            print(f"Tú: {texto}")
        if texto.lower().strip(".!¡ ") in SALIR:
            break
        if texto.lower() == "/olvidar":
            cerebro.olvidar()
            print("JARVIS: Conversación reiniciada.")
            continue

        hud.estado("pensando", texto)
        try:
            respuesta = cerebro.responder(texto)
        except anthropic.APIConnectionError:
            respuesta = "No consigo conectar con mis servidores. Revise la conexión a internet."
        except anthropic.AuthenticationError:
            respuesta = "Mi clave de acceso no es válida. Revise ANTHROPIC_API_KEY."
        except anthropic.RateLimitError:
            respuesta = "Estoy recibiendo demasiadas peticiones. Inténtelo en un momento."
        except anthropic.APIStatusError as error:
            respuesta = f"La API devolvió un error ({error.status_code})."
        except Exception as error:  # errores del modo suscripción (Claude Code)
            if type(error).__module__.split(".")[0] != "claude_agent_sdk":
                raise
            respuesta = f"No consigo hablar con Claude Code: {error}"
        _decir(respuesta, habla, hud)

    if hasattr(cerebro, "cerrar"):
        cerebro.cerrar()
    _decir(f"Hasta luego, {config.nombre_usuario}.", habla, hud)
    hud.cerrar()
    return 0


def _decir(texto: str, habla, hud: HudNulo) -> None:
    """Muestra la respuesta, anima el HUD mientras se pronuncia y lo deja en reposo."""
    print(f"JARVIS: {texto}")
    hud.estado("hablando", texto)
    if habla:
        habla.decir(texto)
        hud.estado("reposo")


def _crear_cerebro(config: Config):
    """Elige entre la API (clave) y la suscripción de Claude (Claude Code con tu sesión)."""
    herramientas = Herramientas(config.carpeta_datos)
    motor = config.motor
    if motor == "auto":
        if _hay_credenciales_api():
            motor = "api"
        elif _hay_sesion_claude():
            motor = "suscripcion"
        elif sys.stdin.isatty():
            motor = _menu_activacion()
        else:
            raise RuntimeError(
                "No encuentro cómo conectar con Claude. Elige una opción:\n"
                "  - Clave de API: copia .env.example como .env y pon tu ANTHROPIC_API_KEY.\n"
                "  - Suscripción Pro/Max: ejecuta `claude` e inicia sesión con /login."
            )
    if motor in ("suscripcion", "suscripción"):
        from .cerebro_suscripcion import CerebroSuscripcion
        print("(usando tu suscripción de Claude a través de Claude Code)")
        return CerebroSuscripcion(config, herramientas)
    if motor != "api":
        raise RuntimeError(f"JARVIS_MOTOR no válido: {config.motor} (usa api, suscripcion o auto)")
    if not _hay_credenciales_api():
        raise RuntimeError("Falta la clave de Claude. Copia .env.example como .env y pon tu ANTHROPIC_API_KEY.")
    try:
        return Cerebro(config, herramientas)
    except anthropic.AnthropicError as error:
        raise RuntimeError(f"No puedo conectar con Claude: {error}") from error


def _menu_activacion() -> str:
    """Pregunta cómo conectar con Claude cuando no hay clave ni suscripción listas.

    Solo guía, y no persiste nada en disco: la clave que pegues vive solo en
    esta ejecución (os.environ) y se pierde al cerrar Jarvis. Si no quieres
    repetirlo cada vez, pon la clave vos mismo en .env.
    """
    print("No encuentro cómo conectar con Claude. ¿Cómo quieres activarlo?")
    print("  1) Ya tengo (o voy a pegar ahora) una clave de API")
    print("  2) Uso mi suscripción Pro/Max de Claude")
    try:
        eleccion = input("Elige 1 o 2: ").strip()
    except (EOFError, KeyboardInterrupt):
        eleccion = ""

    if eleccion == "1":
        clave = getpass.getpass("Pega tu ANTHROPIC_API_KEY (de https://console.anthropic.com): ").strip()
        if not clave:
            raise RuntimeError("No diste ninguna clave. Copia .env.example como .env y pon tu ANTHROPIC_API_KEY.")
        os.environ["ANTHROPIC_API_KEY"] = clave
        print("(clave activa solo para esta sesión; se pierde al cerrar Jarvis)")
        return "api"

    if eleccion == "2":
        if not _hay_sesion_claude():
            raise RuntimeError(
                "Todavía no iniciaste sesión. Hazlo y vuelve a ejecutar python -m jarvis:\n"
                "  claude   (dentro, escribe /login e inicia sesión con tu cuenta)"
            )
        print("(usando tu suscripción de Claude)")
        return "suscripcion"

    raise RuntimeError(
        "No encuentro cómo conectar con Claude. Elige una opción:\n"
        "  - Clave de API: copia .env.example como .env y pon tu ANTHROPIC_API_KEY.\n"
        "  - Suscripción Pro/Max: ejecuta `claude` e inicia sesión con /login."
    )


def _hay_sesion_claude() -> bool:
    """Mejor esfuerzo: ¿ya hiciste `claude` -> /login? No hay forma 100% fiable
    de saberlo sin conectar de verdad, así que mira dónde Claude Code guarda
    la sesión: el llavero en macOS, un archivo en Linux/Windows."""
    if sys.platform == "darwin":
        try:
            resultado = subprocess.run(
                ["security", "find-generic-password", "-s", "Claude Code-credentials"],
                capture_output=True, timeout=5,
            )
            return resultado.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    return (Path.home() / ".claude" / ".credentials.json").is_file()


def _hay_credenciales_api() -> bool:
    """Clave en el entorno o perfil guardado con `ant auth login`."""
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
                or (Path.home() / ".config" / "anthropic").is_dir())


if __name__ == "__main__":
    sys.exit(main())
