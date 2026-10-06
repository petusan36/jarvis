"""Punto de entrada: python -m jarvis [--texto] [--sin-hud] [--silencio] [--pulsar] [--hud]
[--instalar-app] [--reconfigurar-ia].

Por defecto arranca el modo completo: te escucha, te responde hablando y abre
la animación HUD. Usa --texto para el modo clásico de escribir y leer.
--instalar-app crea un ícono de escritorio y termina sin arrancar Jarvis.

El menú de conexión con un modelo de IA corre SIEMPRE en cada arranque normal
(sin --instalar-app), en dos niveles: primero "¿local o proveedor en la
nube?", y solo si elegís proveedor, "¿OpenAI o Anthropic?". Ya no hay un modo
que salte el menú porque detecta algo ya configurado en .env o una sesión
abierta: así podés cambiar de proveedor sin flags extra. Por eso
--reconfigurar-ia quedó sin efecto propio (el menú ya corre siempre) — se
conserva el flag solo para no romper scripts o accesos existentes que lo
invoquen.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
from pathlib import Path

import anthropic

from .cerebro import Cerebro
from .config import Config, guardar_en_env
from .herramientas import Herramientas
from .hud import Hud, HudNulo
from .proveedores import (
    AdaptadorAnthropic,
    AdaptadorCodexResponses,
    AdaptadorOllama,
    MODELO_CODEX_POR_DEFECTO,
    listar_modelos_ollama,
)

SALIR = {"salir", "cerrar", "cierra", "adiós", "adios", "exit", "quit"}


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
    parser.add_argument("--reconfigurar-ia", action="store_true",
                        help="Sin efecto propio: el menú para elegir cómo conectar con un "
                             "modelo de IA ya corre siempre, en cada arranque. Se conserva "
                             "solo por compatibilidad con scripts o accesos que lo invoquen.")
    args = parser.parse_args(argv)

    if args.instalar_app:
        from .escritorio import instalar_app_escritorio
        print(f"Listo: {instalar_app_escritorio()}")
        return 0

    config = Config.desde_entorno()
    if not _tomar_instancia_unica(config.carpeta_datos):
        print("Jarvis ya está abierto (otra instancia sigue corriendo).", file=sys.stderr)
        return 0

    try:
        cerebro = _crear_cerebro(config, forzar_menu=args.reconfigurar_ia)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    config = cerebro.config  # el menú de configuración puede haber actualizado la elección de IA

    try:
        return _ejecutar(args, config, cerebro)
    finally:
        _liberar_instancia(config.carpeta_datos)


def _ejecutar(args, config: Config, cerebro) -> int:
    modo_voz = not args.texto
    usar_hud = (modo_voz and not args.sin_hud) or (not modo_voz and args.hud)

    hud = HudNulo()
    ventana_nativa_url = None
    if usar_hud:
        from .hud import ventana_macos
        nativa = sys.platform == "darwin" and ventana_macos.disponible()
        hud = Hud(config.puerto_hud, abrir_navegador=not nativa)
        print(f"HUD en {hud.url}")
        if nativa:
            ventana_nativa_url = hud.url

    if ventana_nativa_url:
        from .hud import ventana_macos
        resultado = {}

        def trabajo() -> None:
            resultado["codigo"] = _bucle_conversacion(args, config, cerebro, hud)

        ventana_macos.ejecutar_con_ventana_flotante(ventana_nativa_url, trabajo)
        return resultado.get("codigo", 0)

    return _bucle_conversacion(args, config, cerebro, hud)


def _bucle_conversacion(args, config: Config, cerebro, hud: HudNulo) -> int:
    modo_voz = not args.texto
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
        except OSError as error:  # típico de Ollama (no está corriendo) o de Codex (red, sesión vencida)
            respuesta = f"No consigo hablar con el proveedor de IA ({error})."
        except Exception as error:  # errores del modo suscripción (Claude Code)
            if type(error).__module__.split(".")[0] != "claude_agent_sdk":
                raise
            respuesta = f"No consigo hablar con Claude Code: {error}"
        _decir(respuesta, habla, hud, oido)
        if cerebro.herramientas.salir_pedido:
            break

    if hasattr(cerebro, "cerrar"):
        cerebro.cerrar()
    _decir(f"Hasta luego, {config.nombre_usuario}.", habla, hud)
    hud.cerrar()
    return 0


PALABRA_INTERRUPCION = "jarvis"


def _decir(texto: str, habla, hud: HudNulo, oido=None) -> None:
    """Muestra la respuesta, anima el HUD mientras se pronuncia y lo deja en
    reposo. Si hay oído y el motor de voz se puede cortar a mitad de frase,
    escucha en paralelo por si dicen "Jarvis" para interrumpirlo."""
    print(f"JARVIS: {texto}")
    hud.estado("hablando", texto)
    if not habla:
        return
    if oido and habla.interrumpible:
        detener_vigia = threading.Event()
        oido.vigilar_interrupcion(PALABRA_INTERRUPCION, detener_vigia, habla.detener)
        habla.decir(texto)
        detener_vigia.set()
    else:
        habla.decir(texto)
    hud.estado("reposo")


def _crear_cerebro(config: Config, forzar_menu: bool = False):
    """Elige cómo conectar con un modelo de IA: Ollama en local, Claude por
    suscripción (Claude Code) o Codex/OpenAI con la sesión de Codex CLI
    (vía el puerto ``ProveedorIA``, igual que Anthropic/Ollama).

    El menú (``_menu_conexion_ia``) corre SIEMPRE, en cada arranque normal:
    no hay modo "auto" que lo salte por haber algo ya guardado en .env o
    una sesión detectada. ``forzar_menu`` queda como parámetro aceptado por
    compatibilidad (lo pasa ``--reconfigurar-ia``), pero no cambia nada: el
    menú ya corre igual.

    Si elegís un proveedor en la nube (Claude o Codex) y todavía no
    iniciaste sesión, el propio menú dispara el login (ver
    ``_configurar_claude``/``_configurar_codex``) y espera a que termine
    antes de seguir.

    Ya no hay forma de cargar una clave de OpenAI ni de pegar una de
    Anthropic desde el menú: ambas se conectan con la sesión ya logueada
    en su CLI respectiva, nunca con una clave que Jarvis tenga que guardar.
    La única clave que Jarvis todavía puede usar es ANTHROPIC_API_KEY si
    ya está en el entorno (uso directo de la API, sin pasar por ningún
    menú — comportamiento previo a todo esto, sin cambios)."""
    herramientas = Herramientas(config.carpeta_datos, youtube_api_key=config.youtube_api_key)
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Necesito una terminal interactiva para preguntar cómo conectar con un "
            "modelo de IA. Abrí una terminal y ejecutá python -m jarvis (el ícono de "
            "escritorio no sirve para elegir o cambiar de proveedor: solo para arrancar "
            "una vez que ya quedó configurado desde la terminal)."
        )
    motor = _menu_conexion_ia()
    config = Config.desde_entorno()
    if motor in ("suscripcion", "suscripción"):
        from .cerebro_suscripcion import CerebroSuscripcion
        print("(usando tu suscripción de Claude a través de Claude Code)")
        return CerebroSuscripcion(config, herramientas)
    if motor == "codex":
        print("(usando tu sesión de Codex)")
        adaptador = AdaptadorCodexResponses()  # valida la sesión (RuntimeError si no hay o venció)
        if config.modelo == Config().modelo:  # nadie fijó JARVIS_MODELO a mano
            config.modelo = MODELO_CODEX_POR_DEFECTO
        return Cerebro(config, herramientas, adaptador)
    if motor != "api":
        raise RuntimeError(f"JARVIS_MOTOR no válido: {config.motor} (usa api, suscripcion, codex o auto)")
    adaptador = _crear_adaptador(config)
    return Cerebro(config, herramientas, adaptador)


def _crear_adaptador(config: Config):
    """Construye el adaptador de IA (puerto ``ProveedorIA``) según
    ``config.proveedor``: Anthropic con clave directa (sin menú) u Ollama
    local. Codex no es un ``proveedor`` bajo ``motor=api``: tiene su propio
    valor de ``motor`` (``motor=codex``), igual que la suscripción, porque
    no usa clave sino la sesión de Codex CLI — ver ``_crear_cerebro``."""
    if config.proveedor == "anthropic":
        if not _hay_credenciales_api():
            raise RuntimeError("Falta la clave de Claude. Copia .env.example como .env y pon tu ANTHROPIC_API_KEY.")
        try:
            return AdaptadorAnthropic()
        except anthropic.AnthropicError as error:
            raise RuntimeError(f"No puedo conectar con Claude: {error}") from error
    if config.proveedor == "ollama":
        if not config.modelo:
            raise RuntimeError(
                "No hay un modelo local configurado. Ejecuta python -m jarvis --reconfigurar-ia "
                "para elegir uno."
            )
        return AdaptadorOllama(modelo=config.modelo, url=config.ollama_url)
    raise RuntimeError(f"JARVIS_PROVEEDOR no válido: {config.proveedor} (usa anthropic u ollama)")


def _menu_conexion_ia() -> str:
    """Primer nivel del menú de conexión con un modelo de IA: corre en
    todo arranque normal (ver ``_crear_cerebro``). Pregunta primero si el
    modelo es local o un proveedor en la nube; solo si elegís proveedor,
    ``_menu_proveedor_nube`` pregunta cuál. Ninguna opción pide ni guarda
    una clave de API: Claude y Codex usan la sesión que ya iniciaste (o
    que Jarvis inicia por vos, ver ``_configurar_claude``/
    ``_configurar_codex``) en su CLI, y Ollama no necesita clave. Solo se
    persiste en .env la elección en sí (qué motor usar, qué modelo local),
    nunca un secreto.
    """
    print("¿Cómo querés conectar con un modelo de IA?")
    print("  1) Un modelo local (Ollama)")
    print("  2) Un proveedor en la nube")
    try:
        eleccion = input("Elige 1 o 2: ").strip()
    except (EOFError, KeyboardInterrupt):
        eleccion = ""

    if eleccion == "1":
        return _configurar_local()
    if eleccion == "2":
        return _menu_proveedor_nube()

    raise RuntimeError(
        "No encuentro cómo conectar con un modelo de IA. Elige una opción:\n"
        "  - Modelo local: instala Ollama y descarga un modelo (ollama pull qwen3:8b).\n"
        "  - Claude: ejecuta `claude` e inicia sesión con /login.\n"
        "  - Codex: ejecuta `codex login` (instala antes Codex CLI si falta)."
    )


def _menu_proveedor_nube() -> str:
    """Segundo nivel del menú, solo si en el primero se eligió "proveedor
    en la nube". Si no hay sesión activa todavía, la opción elegida
    dispara el login ella misma (ver ``_configurar_claude`` /
    ``_configurar_codex``)."""
    print("¿Qué proveedor en la nube?")
    print("  1) OpenAI (Codex, con tu sesión de Codex CLI)")
    print("  2) Anthropic (Claude, con tu sesión de Claude Code)")
    try:
        eleccion = input("Elige 1 o 2: ").strip()
    except (EOFError, KeyboardInterrupt):
        eleccion = ""

    if eleccion == "1":
        return _configurar_codex()
    if eleccion == "2":
        return _configurar_claude()

    raise RuntimeError(
        "No encuentro cómo conectar con un modelo de IA. Elige una opción:\n"
        "  - OpenAI: ejecuta `codex login` (instala antes Codex CLI si falta).\n"
        "  - Anthropic: ejecuta `claude` e inicia sesión con /login."
    )


def _configurar_local() -> str:
    """Lista los modelos instalados en Ollama y deja elegir uno."""
    try:
        modelos = listar_modelos_ollama()
    except OSError as error:
        raise RuntimeError(
            f"No consigo hablar con Ollama ({error}). ¿Está corriendo? Probá "
            "`ollama serve`, o instalalo desde https://ollama.com."
        ) from error
    if not modelos:
        raise RuntimeError(
            "Ollama está corriendo pero no tiene modelos instalados. Probá `ollama pull qwen3:8b`."
        )

    print("Modelos locales instalados:")
    for i, nombre in enumerate(modelos, start=1):
        print(f"  {i}) {nombre}")
    try:
        indice = int(input(f"Elige 1-{len(modelos)}: ").strip()) - 1
        if indice < 0:
            raise ValueError
        modelo = modelos[indice]
    except (ValueError, IndexError, EOFError, KeyboardInterrupt) as error:
        raise RuntimeError("No elegiste un modelo local válido.") from error

    guardar_en_env("JARVIS_PROVEEDOR", "ollama")
    guardar_en_env("JARVIS_MODELO", modelo)
    guardar_en_env("JARVIS_MOTOR", "api")
    os.environ["JARVIS_PROVEEDOR"] = "ollama"
    os.environ["JARVIS_MODELO"] = modelo
    os.environ["JARVIS_MOTOR"] = "api"
    print(f"(usando el modelo local {modelo}; elección guardada en .env)")
    return "api"


def _configurar_claude() -> str:
    """Usa tu sesión de Claude Code (sin clave de API). Si todavía no
    iniciaste sesión, Jarvis mismo la dispara en vez de pedirte que abras
    otra terminal.

    Verificado con ``claude --help`` en esta máquina: Claude Code NO tiene
    un subcomando de login no interactivo (no existe ``claude login``).
    Todo el flujo de /login vive dentro de la sesión interactiva del REPL.
    Por eso el mejor esfuerzo real posible — y lo que se implementa acá —
    es lanzar `claude` como subproceso heredando stdin/stdout/stderr del
    usuario: así ve el prompt de Claude Code, escribe /login, completa el
    OAuth en el navegador, y vuelve a la terminal con /exit o Ctrl+D. Jarvis
    espera a que ese subproceso termine y recién ahí verifica con
    ``_hay_sesion_claude()`` si quedó una sesión activa — no hay forma más
    fiable de confirmarlo sin esto."""
    if not _hay_sesion_claude():
        print(
            "No encuentro una sesión de Claude Code. Voy a abrir `claude`: una vez "
            "dentro, escribe /login, completa el inicio de sesión en el navegador y "
            "después /exit (o Ctrl+D) para volver aquí."
        )
        try:
            subprocess.run(["claude"])
        except OSError as error:
            raise RuntimeError(
                f"No pude ejecutar `claude` ({error}). ¿Está instalado? Instalalo con "
                "npm install -g @anthropic-ai/claude-code o desde "
                "https://docs.claude.com/claude-code."
            ) from error
        if not _hay_sesion_claude():
            raise RuntimeError(
                "No quedó una sesión activa de Claude Code después de /login. Volvé a "
                "intentar: ejecuta python -m jarvis de nuevo y completá el inicio de "
                "sesión dentro de `claude`."
            )
    guardar_en_env("JARVIS_MOTOR", "suscripcion")
    os.environ["JARVIS_MOTOR"] = "suscripcion"
    print("(usando tu suscripción de Claude; elección guardada en .env)")
    return "suscripcion"


def _configurar_codex() -> str:
    """Usa tu sesión de Codex CLI (sin clave de API): habla directo contra
    el endpoint que usa el propio Codex CLI, no contra la CLI en sí, así
    que no hace falta tenerla instalada para usar Jarvis — solo para hacer
    login. Si no hay sesión, Jarvis mismo la dispara.

    A diferencia de Claude Code, Codex CLI SÍ tiene un subcomando directo
    para loguearse: `codex login` (confirmado con `codex --help` en esta
    máquina). Igual que con Claude, se lanza como subproceso heredando
    stdin/stdout/stderr del usuario, porque el flujo abre el navegador para
    el OAuth y necesita esa interacción; Jarvis espera a que termine y
    verifica con ``_hay_sesion_codex()`` si la sesión quedó activa (el
    archivo de sesión queda en ~/.codex/auth.json)."""
    if not _hay_sesion_codex():
        print(
            "No encuentro una sesión de Codex. Voy a ejecutar `codex login`: "
            "completa el inicio de sesión en el navegador que se abra."
        )
        try:
            subprocess.run(["codex", "login"])
        except OSError as error:
            raise RuntimeError(
                f"No pude ejecutar `codex login` ({error}). ¿Está instalado Codex CLI? "
                "Instalalo con: npm install -g @openai/codex"
            ) from error
        if not _hay_sesion_codex():
            raise RuntimeError(
                "No quedó una sesión activa de Codex después de `codex login`. Volvé a "
                "intentar: ejecuta python -m jarvis de nuevo y completá el inicio de "
                "sesión."
            )
    guardar_en_env("JARVIS_MOTOR", "codex")
    os.environ["JARVIS_MOTOR"] = "codex"
    print("(usando tu sesión de Codex; elección guardada en .env)")
    return "codex"


def _tomar_instancia_unica(carpeta_datos: Path) -> bool:
    """Evita abrir dos Jarvis a la vez (ej. doble clic repetido en el ícono).

    Devuelve False si ya hay una instancia viva. Un .pid de un proceso muerto
    (cierre sucio, apagón) se ignora solo: no hace falta borrarlo a mano.
    """
    ruta = carpeta_datos / "jarvis.pid"
    if ruta.is_file():
        try:
            pid_anterior = int(ruta.read_text().strip())
            os.kill(pid_anterior, 0)
            return False  # el proceso sigue vivo
        except ProcessLookupError:
            pass  # el proceso ya no existe: .pid viejo de un cierre sucio
        except (ValueError, OSError):
            pass  # .pid corrupto, o el SO no deja preguntar (ej. permisos, Windows): seguimos
    carpeta_datos.mkdir(parents=True, exist_ok=True)
    ruta.write_text(str(os.getpid()))
    return True


def _liberar_instancia(carpeta_datos: Path) -> None:
    ruta = carpeta_datos / "jarvis.pid"
    try:
        if int(ruta.read_text().strip()) == os.getpid():
            ruta.unlink()
    except (OSError, ValueError):
        pass  # ya no está, o es de otra instancia: no tocar


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


def _hay_sesion_codex() -> bool:
    """Mejor esfuerzo: ¿ya hiciste `codex login`? Igual que con Claude, no
    hay forma 100% fiable de saberlo sin conectar de verdad; miramos el
    archivo donde Codex CLI guarda la sesión por defecto. Si configuraste
    ``storage=keyring``, la sesión vive en el keychain del sistema y esto
    no la va a detectar — no pasa nada: Codex CLI mismo avisa si no hay
    sesión cuando corre ``codex exec``."""
    return (Path.home() / ".codex" / "auth.json").is_file()


def _hay_credenciales_api() -> bool:
    """Clave en el entorno o perfil guardado con `ant auth login`."""
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
                or (Path.home() / ".config" / "anthropic").is_dir())


if __name__ == "__main__":
    sys.exit(main())
