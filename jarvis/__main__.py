"""Punto de entrada: python -m jarvis [--voz] [--silencio] [--pulsar] [--hud]."""

from __future__ import annotations

import argparse
import importlib.util
import os
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
    parser.add_argument("--voz", action="store_true",
                        help="Escuchar por el micrófono y responder hablando (por defecto: modo texto).")
    parser.add_argument("--silencio", action="store_true",
                        help="En modo voz, responder solo por texto (sin síntesis).")
    parser.add_argument("--pulsar", action="store_true",
                        help="En modo voz, pulsar Enter para hablar en lugar de escuchar siempre.")
    parser.add_argument("--hud", action="store_true",
                        help="Abrir en el navegador la animación estilo Jarvis (anillos que reaccionan).")
    args = parser.parse_args(argv)

    config = Config.desde_entorno()
    try:
        cerebro = _crear_cerebro(config)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    hud = HudNulo()
    if args.hud:
        hud = Hud(config.puerto_hud)
        print(f"HUD en {hud.url}")

    oido = habla = None
    if args.voz:
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
        elif importlib.util.find_spec("claude_agent_sdk") is not None:
            motor = "suscripcion"
        else:
            raise RuntimeError(
                "No encuentro cómo conectar con Claude. Elige una opción:\n"
                "  - Clave de API: copia .env.example como .env y pon tu ANTHROPIC_API_KEY.\n"
                "  - Suscripción Pro/Max: pip install -e '.[suscripcion]' e inicia sesión con `claude`."
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


def _hay_credenciales_api() -> bool:
    """Clave en el entorno o perfil guardado con `ant auth login`."""
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
                or (Path.home() / ".config" / "anthropic").is_dir())


if __name__ == "__main__":
    sys.exit(main())
