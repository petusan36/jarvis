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

Cómo se muestra ese menú depende solo de si hay una terminal interactiva
real (``sys.stdin.isatty()``), nunca de --texto ni de ningún otro flag: si
hay tty (ejecutaste `python -m jarvis` a mano, con o sin --texto), el menú
es por input()/print() en esa misma terminal, como siempre. Si no hay tty
(ej. doble clic en el ícono de --instalar-app, sin terminal real) pero hay
entorno gráfico disponible (hoy: macOS con PyObjC), se abre en cambio una
ventana nativa con el mismo menú de 2 niveles (ver
``_menu_conexion_ia_ventana`` en ``jarvis.conexion_ia`` y
``jarvis.hud.servidor_menu``/``jarvis.hud.ventana_macos``). Si no hay ni
tty ni entorno gráfico, falla con un error claro: no hay forma de
preguntar nada.

El menú y el login de proveedores en la nube viven en ``jarvis.conexion_ia``;
el lock de instancia única y la redirección de log del bundle viven en
``jarvis.instancia`` — ver auditoría de arquitectura hexagonal.
"""

from __future__ import annotations

import argparse
import sys
import threading

import anthropic

from .config import Config
from .conexion_ia import _crear_cerebro
from .hud import Hud, HudNulo
from .instancia import _liberar_instancia, _redirigir_log_si_es_bundle_standalone, _tomar_instancia_unica

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
    parser.add_argument("--enrolar-voz", action="store_true",
                        help="Graba tu voz de referencia para el reconocimiento de hablante "
                             "(ver jarvis.voz.hablante) y termina. Repetilo para reemplazarla.")
    args = parser.parse_args(argv)

    if args.enrolar_voz:
        from .voz.hablante import enrolar_voz
        config = Config.desde_entorno()
        try:
            enrolar_voz(config)
        except RuntimeError as error:
            print(error, file=sys.stderr)
            return 1
        return 0

    if args.instalar_app:
        from .escritorio import instalar_app_escritorio
        try:
            print(f"Listo: {instalar_app_escritorio()}")
        except RuntimeError as error:
            print(error, file=sys.stderr)
            return 1
        return 0

    config = Config.desde_entorno()
    _redirigir_log_si_es_bundle_standalone(config.carpeta_datos)
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
            resultado["codigo"] = _bucle_conversacion(
                args, config, cerebro, hud,
                al_dormir=ventana_macos.ocultar_ventana, al_despertar=ventana_macos.mostrar_ventana,
            )

        ventana_macos.ejecutar_con_ventana_flotante(ventana_nativa_url, trabajo)
        return resultado.get("codigo", 0)

    return _bucle_conversacion(args, config, cerebro, hud)


def _bucle_conversacion(args, config: Config, cerebro, hud: HudNulo, oido=None, habla=None,
                        al_dormir=lambda: None, al_despertar=lambda: None) -> int:
    """``al_dormir``/``al_despertar``: ganchos opcionales para el modo de
    escucha pasiva (ver jarvis.voz.oido.Oido.dormir y la herramienta
    "dormir_jarvis") — en modo ventana nativa, ocultan/muestran la ventana
    del HUD; en cualquier otro caso quedan en no-op."""
    modo_voz = not args.texto
    if modo_voz:
        if oido is None:
            from .voz.oido import Oido
            verificador, referencia_voz = _cargar_reconocimiento_voz(config)
            oido = Oido(config.modelo_whisper, config.idioma, hud, pulsar=args.pulsar,
                        palabra_activacion=config.palabra_activacion,
                        sensibilidad=config.sensibilidad_voz,
                        verificador=verificador, referencia_voz=referencia_voz,
                        segundos_reposo_inactividad=config.segundos_reposo_inactividad,
                        al_dormir=al_dormir, al_despertar=al_despertar)
        if not args.silencio and habla is None:
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
        es_dueño = oido.es_dueño if oido else True
        try:
            respuesta = cerebro.responder(texto, es_dueño)
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
        if cerebro.herramientas.dormir_pedido:
            if oido:
                oido.dormir()
            cerebro.herramientas.dormir_pedido = False
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


def _cargar_reconocimiento_voz(config: Config):
    """Construye el verificador de hablante (ver jarvis.voz.hablante), solo
    si está habilitado Y ya hay una voz enrolada (``jarvis --enrolar-voz``).
    Sin eso (deshabilitado, o nadie enroló nada todavía), (None, None): no
    se exige nada, como siempre. Pero si SÍ hay una voz enrolada y el
    verificador real no carga (falta instalar el soporte, modelo corrupto,
    etc.), falla cerrado con VerificadorRoto en vez de abierto — el usuario
    pidió este chequeo, así que una falla no debe desactivarlo en
    silencio."""
    if not config.reconocimiento_voz_habilitado:
        return None, None
    from .voz.hablante import VerificadorHablante, VerificadorRoto, cargar_referencia, ruta_referencia

    referencia = cargar_referencia(ruta_referencia(config.carpeta_datos))
    if referencia is None:
        return None, None
    try:
        verificador = VerificadorHablante(umbral=config.umbral_voz_dueño)
    except RuntimeError as error:
        print(
            f"(reconocimiento de voz: {error} — las herramientas que requieren tu voz "
            "se van a negar hasta que esto se arregle)",
            file=sys.stderr,
        )
        return VerificadorRoto(), referencia
    return verificador, referencia


if __name__ == "__main__":
    sys.exit(main())
