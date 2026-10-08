"""Conexión con un modelo de IA: elegir motor/proveedor (menú de consola o
de ventana nativa) y disparar el login de los proveedores en la nube
(Claude Code, Codex CLI).

Separado de __main__.py: ese módulo mezclaba el arranque de Jarvis (CLI,
instancia única, bucle de conversación) con toda esta lógica de conexión
con la IA, que no tiene nada que ver con lo anterior.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import anthropic

from .cerebro import Cerebro
from .config import Config, guardar_en_env
from .herramientas import Herramientas
from .proveedores import (
    AdaptadorAnthropic,
    AdaptadorCodexResponses,
    AdaptadorOllama,
    MODELO_CODEX_POR_DEFECTO,
    listar_modelos_ollama,
)

TIMEOUT_LOGIN_VENTANA_SEGUNDOS = 180  # cuánto esperar, pollendo, un login en la Terminal que se abrió
ESPERA_ENTRE_POLLEOS_SEGUNDOS = 1.5


def _crear_memoria(config: Config):
    """Construye el adaptador de memoria permanente (graphiti + ladybug +
    Ollama). Importado de forma perezosa: si ``memoria_habilitada`` es
    False (comportamiento por defecto), estas dependencias pesadas nunca
    se cargan."""
    from .memoria import AdaptadorMemoriaGraphiti

    return AdaptadorMemoriaGraphiti(
        config.carpeta_datos / "memoria",
        ollama_url=config.ollama_url,
        modelo_llm=config.memoria_modelo_llm,
        modelo_embedding=config.memoria_modelo_embedding,
        ventana_gracia_dias=config.memoria_ventana_gracia_dias,
    )


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
    if sys.stdin.isatty():
        # Hay una terminal real (ej. corriste `python -m jarvis` a mano): el
        # menú de siempre, por input()/print(). Esto no cambia aunque haya
        # ventana gráfica disponible — si alguien corre Jarvis desde la
        # terminal a propósito, se respeta eso y no se le tapa con una
        # ventana encima.
        motor = _menu_conexion_ia()
    elif sys.platform == "darwin" and _hud_ventana_disponible():
        # Sin terminal (ej. doble clic en el ícono de escritorio) pero con
        # entorno gráfico disponible: se muestra una ventana nativa con el
        # mismo menú de 2 niveles en vez de romper por falta de tty.
        motor = _menu_conexion_ia_ventana()
    else:
        raise RuntimeError(
            "Necesito una terminal interactiva (o una ventana gráfica, solo "
            "disponible hoy en macOS con PyObjC) para preguntar cómo conectar "
            "con un modelo de IA. Abrí una terminal y ejecutá python -m jarvis."
        )
    config = Config.desde_entorno()
    # Construida DESPUÉS del menú, con el config final: si Herramientas se
    # construyera antes (con el config de antes del menú), guardar_nombre
    # mutaría un objeto Config que Cerebro ya no usa — el nombre quedaría
    # bien guardado en .env, pero nunca se vería en lo que queda de esta
    # sesión (confirmado en vivo: Jarvis seguía despidiéndose con el
    # nombre viejo después de confirmar uno nuevo).
    herramientas = Herramientas(
        config.carpeta_datos,
        youtube_api_key=config.youtube_api_key,
        memoria=_crear_memoria(config) if config.memoria_habilitada else None,
        config=config,
    )
    # config.modelo/JARVIS_MODELO es un solo campo compartido entre los tres
    # motores, pero cada uno tiene su propio espacio de nombres de modelos
    # (tags de Ollama como "qwen3:8b", nombres de Claude, nombres de Codex)
    # — si quedó fijado para Ollama (motor=api) y después se elige
    # suscripción o Codex, NO sirve para el motor nuevo. Confirmado en vivo:
    # Codex devolvía 400 ("'qwen3:8b' no soportado") porque _crear_cerebro
    # mandaba ese valor tal cual. _es_modelo_ollama (heurística: los tags de
    # Ollama llevan ":", los de Claude/Codex no) decide si hay que ignorarlo
    # y usar el default del motor nuevo en vez de "¿sigue en el default
    # genérico?" (que no detecta este caso: un modelo de Ollama elegido a
    # propósito no es el default genérico, pero tampoco sirve acá).
    if motor in ("suscripcion", "suscripción"):
        from .cerebro_suscripcion import CerebroSuscripcion
        print("(usando tu suscripción de Claude a través de Claude Code)")
        if _es_modelo_ollama(config.modelo):
            config.modelo = Config().modelo
        return CerebroSuscripcion(config, herramientas)
    if motor == "codex":
        print("(usando tu sesión de Codex)")
        adaptador = AdaptadorCodexResponses()  # valida la sesión (RuntimeError si no hay o venció)
        if config.modelo == Config().modelo or _es_modelo_ollama(config.modelo):
            config.modelo = MODELO_CODEX_POR_DEFECTO
        return Cerebro(config, herramientas, adaptador)
    if motor != "api":
        raise RuntimeError(f"JARVIS_MOTOR no válido: {config.motor} (usa api, suscripcion, codex o auto)")
    adaptador = _crear_adaptador(config)
    return Cerebro(config, herramientas, adaptador)


def _es_modelo_ollama(modelo: str) -> bool:
    """¿Este valor de config.modelo es un tag de Ollama ("qwen3:8b",
    "llama3.1:8b"...), no un nombre de modelo de Claude/Codex? Los tags de
    Ollama siempre llevan ":" (repo:tag); los nombres de Claude/Codex,
    nunca — heurística simple, pero alcanza para detectar el caso real:
    un modelo elegido para motor=api/proveedor=ollama que quedó guardado
    en JARVIS_MODELO y no sirve si después se elige otro motor."""
    return ":" in modelo


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

    resultado = _guardar_eleccion_local(modelo)
    print(f"(usando el modelo local {modelo}; elección guardada en .env)")
    return resultado


def _guardar_eleccion_local(modelo: str) -> str:
    """Persiste la elección de modelo local, sin ningún print ni input: la
    parte que comparten el menú de consola (``_configurar_local``) y el de
    ventana (``_atender_menu_local_ventana``)."""
    guardar_en_env("JARVIS_PROVEEDOR", "ollama")
    guardar_en_env("JARVIS_MODELO", modelo)
    guardar_en_env("JARVIS_MOTOR", "api")
    os.environ["JARVIS_PROVEEDOR"] = "ollama"
    os.environ["JARVIS_MODELO"] = modelo
    os.environ["JARVIS_MOTOR"] = "api"
    return "api"


def _guardar_motor(motor: str) -> str:
    """Persiste solo el motor elegido (suscripción Claude o Codex), sin
    clave alguna: la parte que comparten ``_configurar_claude``/
    ``_configurar_codex`` (consola) y ``_atender_login_ventana`` (ventana)."""
    guardar_en_env("JARVIS_MOTOR", motor)
    os.environ["JARVIS_MOTOR"] = motor
    return motor


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
    resultado = _guardar_motor("suscripcion")
    print("(usando tu suscripción de Claude; elección guardada en .env)")
    return resultado


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
    resultado = _guardar_motor("codex")
    print("(usando tu sesión de Codex; elección guardada en .env)")
    return resultado


def _hud_ventana_disponible() -> bool:
    from .hud import ventana_macos
    return ventana_macos.disponible()


def _menu_conexion_ia_ventana() -> str:
    """Equivalente a ``_menu_conexion_ia`` pero mostrando una ventana nativa
    en vez de preguntar por la terminal: se usa cuando no hay tty (ej. el
    ícono de escritorio) pero sí hay entorno gráfico (ver
    ``_crear_cerebro``). La ventana corre en el hilo principal (lo exige
    AppKit) mientras este hilo de trabajo atiende los clics y la lógica de
    siempre (listar modelos, disparar login, verificar sesión) en un hilo
    aparte — ver ``ventana_macos.ejecutar_ventana_menu``."""
    from .hud import ventana_macos
    from .hud.servidor_menu import ServidorMenu

    servidor = ServidorMenu()
    resultado: dict[str, str] = {}

    def trabajo() -> None:
        try:
            resultado["motor"] = _atender_menu_ventana(servidor)
        except Exception as error:  # noqa: BLE001 — se re-lanza abajo, ya fuera de la ventana
            resultado["error"] = str(error)
            servidor.actualizar(paso="error", mensaje=str(error))
            time.sleep(2.5)  # deja el mensaje de error visible un instante antes de cerrar
        finally:
            servidor.cerrar()

    ventana_macos.ejecutar_ventana_menu(servidor.url, trabajo)
    if "error" in resultado:
        raise RuntimeError(resultado["error"])
    return resultado["motor"]


def _atender_menu_ventana(servidor) -> str:
    """Primer nivel del menú en ventana: local o proveedor en la nube."""
    servidor.actualizar(paso="inicio")
    accion = servidor.esperar_accion(timeout=TIMEOUT_LOGIN_VENTANA_SEGUNDOS)
    if not accion or accion.get("tipo") not in ("local", "proveedor"):
        raise RuntimeError("No se eligió cómo conectar con un modelo de IA (se agotó el tiempo de espera).")

    if accion["tipo"] == "local":
        return _atender_menu_local_ventana(servidor)
    return _atender_menu_proveedor_ventana(servidor)


def _atender_menu_local_ventana(servidor) -> str:
    """Lista los modelos de Ollama en la ventana y espera a que elijan uno."""
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

    servidor.actualizar(paso="local", modelos=modelos)
    accion = servidor.esperar_accion(timeout=TIMEOUT_LOGIN_VENTANA_SEGUNDOS)
    if not accion or accion.get("tipo") != "modelo" or accion.get("modelo") not in modelos:
        raise RuntimeError("No elegiste un modelo local válido.")

    resultado = _guardar_eleccion_local(accion["modelo"])
    servidor.actualizar(paso="hecho", mensaje=f"Usando el modelo local {accion['modelo']}.")
    # El camino de consola (_configurar_local) ya imprime esto; el de
    # ventana no lo hacía — sin esto, el log nunca decía qué proveedor
    # eligieron desde el ícono de escritorio, imposible de diagnosticar.
    print(f"(usando el modelo local {accion['modelo']}; elección guardada en .env)")
    return resultado


def _atender_menu_proveedor_ventana(servidor) -> str:
    """Segundo nivel del menú en ventana: OpenAI o Anthropic."""
    servidor.actualizar(paso="proveedor")
    accion = servidor.esperar_accion(timeout=TIMEOUT_LOGIN_VENTANA_SEGUNDOS)
    if not accion or accion.get("tipo") not in ("openai", "anthropic"):
        raise RuntimeError("No se eligió un proveedor en la nube (se agotó el tiempo de espera).")

    if accion["tipo"] == "openai":
        return _atender_login_ventana(
            servidor, hay_sesion=_hay_sesion_codex, comando=["codex", "login"],
            motor="codex", nombre="Codex",
        )
    return _atender_login_ventana(
        servidor, hay_sesion=_hay_sesion_claude, comando=["claude"],
        motor="suscripcion", nombre="Claude Code",
    )


def _atender_login_ventana(servidor, *, hay_sesion, comando: list[str], motor: str, nombre: str) -> str:
    """Dispara (si hace falta) el login de un proveedor en la nube desde la
    ventana. A diferencia del menú de consola (``_configurar_claude``/
    ``_configurar_codex``), acá Jarvis NO tiene una terminal propia que
    heredar (arrancó desde el ícono de escritorio, sin stdin/stdout real):
    por eso abre una Terminal.app visible con el comando de login (patrón
    estándar en macOS vía ``osascript``/AppleScript) y, mientras tanto,
    pollea ``hay_sesion()`` sin bloquear la ventana hasta detectar que el
    login terminó o se agota ``TIMEOUT_LOGIN_VENTANA_SEGUNDOS``."""
    if hay_sesion():
        servidor.actualizar(paso="hecho", mensaje=f"Ya había una sesión de {nombre} activa.")
        print(f"(ya había sesión de {nombre} activa; usando motor={motor})")
        return _guardar_motor(motor)

    servidor.actualizar(
        paso="esperando_login",
        mensaje=(
            f"Abriendo una Terminal para iniciar sesión en {nombre}. Completá el "
            "inicio de sesión ahí (incluyendo el navegador si lo pide); esta "
            "ventana sigue solo y se cierra cuando termines."
        ),
    )
    try:
        _abrir_terminal_con_comando(comando)
    except OSError as error:
        raise RuntimeError(
            f"No pude abrir una Terminal para `{' '.join(comando)}` ({error})."
        ) from error

    limite = time.monotonic() + TIMEOUT_LOGIN_VENTANA_SEGUNDOS
    while time.monotonic() < limite:
        if hay_sesion():
            servidor.actualizar(paso="hecho", mensaje=f"Sesión de {nombre} activa.")
            print(f"(login de {nombre} completado; usando motor={motor})")
            return _guardar_motor(motor)
        time.sleep(ESPERA_ENTRE_POLLEOS_SEGUNDOS)

    raise RuntimeError(
        f"No detecté una sesión activa de {nombre} después de "
        f"{TIMEOUT_LOGIN_VENTANA_SEGUNDOS}s. Completá el inicio de sesión en la "
        "Terminal que se abrió y volvé a abrir Jarvis."
    )


def _abrir_terminal_con_comando(comando: list[str]) -> None:
    """Abre una Terminal.app visible corriendo ``comando``: es el único
    camino real para un login interactivo (OAuth en el navegador) cuando
    Jarvis no tiene su propia terminal para heredar (ver
    ``_atender_login_ventana``). Patrón estándar en macOS: pedirle a
    Terminal.app, vía AppleScript, que corra el comando. No usa
    ``capture_output``/``check``: solo hace falta disparar la ventana, no
    esperar a que el proceso de ``osascript`` en sí termine ni leer su
    salida (abre la Terminal y vuelve enseguida)."""
    guion = " ".join(shlex.quote(parte) for parte in comando)
    aplescript = f'tell application "Terminal" to do script "{guion}"'
    subprocess.run(["osascript", "-e", aplescript], timeout=10, check=True)


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
