"""Pruebas sin red: se sustituye el cliente de Claude por uno falso."""

import os
from types import SimpleNamespace as NS

import pytest

from jarvis.__main__ import main
from jarvis.cerebro import Cerebro
from jarvis.config import Config
from jarvis.herramientas import Herramientas, evaluar_expresion
from jarvis.proveedores import AdaptadorAnthropic


class ClienteFalso:
    """Imita client.beta.messages.create devolviendo respuestas preparadas."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.peticiones = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.peticiones.append(kwargs)
        return self.respuestas.pop(0)


def texto(t):
    return NS(type="text", text=t)


def uso(nombre, entrada, id_="t1"):
    return NS(type="tool_use", id=id_, name=nombre, input=entrada)


@pytest.fixture
def herramientas(tmp_path):
    return Herramientas(tmp_path)


def test_calculadora_segura():
    assert evaluar_expresion("(2+3)*sqrt(16)") == 20
    assert evaluar_expresion("2^10") == 1024
    with pytest.raises(ValueError):
        evaluar_expresion("__import__('os').system('ls')")


def test_notas(herramientas):
    assert herramientas.ejecutar("leer_notas", {}) == ("No hay notas guardadas.", False)
    herramientas.ejecutar("guardar_nota", {"texto": "comprar leche"})
    salida, error = herramientas.ejecutar("leer_notas", {})
    assert "comprar leche" in salida and not error


def test_cerrar_jarvis_marca_salida_pedida(herramientas):
    assert herramientas.salir_pedido is False
    salida, error = herramientas.ejecutar("cerrar_jarvis", {})
    assert not error
    assert herramientas.salir_pedido is True


def test_herramienta_desconocida(herramientas):
    assert herramientas.ejecutar("volar", {})[1] is True


def test_definiciones_validas(herramientas):
    for d in herramientas.definiciones():
        assert d["input_schema"]["additionalProperties"] is False
        assert set(d["input_schema"]["required"]) == set(d["input_schema"]["properties"])


def test_cerebro_usa_herramienta(herramientas):
    cliente = ClienteFalso([
        NS(stop_reason="tool_use", content=[uso("calcular", {"expresion": "6*7"})]),
        NS(stop_reason="end_turn", content=[texto("Son 42, señor.")]),
    ])
    cerebro = Cerebro(Config(), herramientas, AdaptadorAnthropic(cliente))

    assert cerebro.responder("¿Cuánto es 6 por 7?") == "Son 42, señor."
    resultado = cerebro.historial[2].resultados[0]
    assert resultado.contenido == "42" and not resultado.es_error
    assert cliente.peticiones[0]["model"] == "claude-opus-5-5"


def test_cerebro_rechazo(herramientas):
    cliente = ClienteFalso([NS(stop_reason="refusal", content=[])])
    cerebro = Cerebro(Config(), herramientas, AdaptadorAnthropic(cliente))
    assert "no puedo" in cerebro.responder("algo").lower()


def test_modo_texto_de_principio_a_fin(monkeypatch, tmp_path, capsys):
    cliente = ClienteFalso([NS(stop_reason="end_turn", content=[texto("Todo en orden, señor.")])])
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.setattr("jarvis.proveedores.anthropic_adaptador.anthropic.Anthropic", lambda: cliente)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("jarvis.conexion_ia._menu_conexion_ia", lambda: "api")
    entradas = iter(["hola", "salir"])
    monkeypatch.setattr("builtins.input", lambda _="": next(entradas))

    assert main(["--texto"]) == 0
    salida = capsys.readouterr().out
    assert "JARVIS: Todo en orden, señor." in salida
    assert "Hasta luego" in salida


def test_jarvis_se_cierra_solo_por_decision_de_claude(monkeypatch, tmp_path, capsys):
    cliente = ClienteFalso([
        NS(stop_reason="tool_use", content=[uso("cerrar_jarvis", {})]),
        NS(stop_reason="end_turn", content=[texto("Hasta luego, señor.")]),
    ])
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.setattr("jarvis.proveedores.anthropic_adaptador.anthropic.Anthropic", lambda: cliente)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("jarvis.conexion_ia._menu_conexion_ia", lambda: "api")
    entradas = iter(["ya terminamos por hoy, cerrate"])  # nunca dice "salir" literal
    monkeypatch.setattr("builtins.input", lambda _="": next(entradas))

    # Si no cortara el bucle, el segundo input() agotaría el iterador y fallaría el test.
    assert main(["--texto"]) == 0
    salida = capsys.readouterr().out
    assert "JARVIS: Hasta luego, señor." in salida


def test_hud_envia_estados_al_navegador():
    import json
    import urllib.request

    from jarvis.hud import Hud

    hud = Hud(puerto=0, abrir_navegador=False)
    try:
        with urllib.request.urlopen(hud.url, timeout=5) as pagina:
            assert b"<canvas" in pagina.read()
        with urllib.request.urlopen(hud.url + "eventos", timeout=5) as eventos:
            def siguiente():
                linea = eventos.readline()
                eventos.readline()  # línea en blanco que separa eventos
                return json.loads(linea.decode().removeprefix("data: "))

            assert siguiente()["estado"] == "reposo"
            hud.estado("pensando", "¿qué hora es?")
            assert siguiente() == {"tipo": "estado", "estado": "pensando", "texto": "¿qué hora es?"}
            hud.nivel(3)
            assert siguiente() == {"tipo": "nivel", "valor": 1.0}
            hud.estado("hablando")
            assert siguiente()["texto"] == "¿qué hora es?"  # sin texto nuevo, se conserva el anterior
        with pytest.raises(ValueError):
            hud.estado("bailando")
    finally:
        hud.cerrar()


def test_abrir_ventana_app_usa_chrome_si_esta(monkeypatch):
    from jarvis import hud as hud_mod

    llamadas = []
    monkeypatch.setattr(hud_mod, "_navegador_con_modo_app", lambda: "/usr/bin/chrome")
    monkeypatch.setattr(hud_mod.subprocess, "Popen", lambda args, **kw: llamadas.append(args))
    monkeypatch.setattr(hud_mod.webbrowser, "open", lambda url: pytest.fail("no debería caer a pestaña"))

    hud_mod._abrir_ventana_app("http://127.0.0.1:8765/")

    assert llamadas == [["/usr/bin/chrome", "--app=http://127.0.0.1:8765/", "--window-size=480,480"]]


def test_abrir_ventana_app_cae_a_pestana_sin_navegador(monkeypatch):
    from jarvis import hud as hud_mod

    abiertas = []
    monkeypatch.setattr(hud_mod, "_navegador_con_modo_app", lambda: None)
    monkeypatch.setattr(hud_mod.webbrowser, "open", lambda url: abiertas.append(url))

    hud_mod._abrir_ventana_app("http://127.0.0.1:8765/")

    assert abiertas == ["http://127.0.0.1:8765/"]


def test_modo_texto_con_hud(monkeypatch, tmp_path):
    estados = []

    class HudFalso:
        url = "http://127.0.0.1:0/"

        def __init__(self, *_args, **_kwargs):
            pass

        def estado(self, nombre, texto=None):
            estados.append(nombre)

        def nivel(self, valor):
            pass

        def cerrar(self):
            estados.append("cerrado")

    cliente = ClienteFalso([NS(stop_reason="end_turn", content=[texto("Todo en orden, señor.")])])
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.setattr("jarvis.proveedores.anthropic_adaptador.anthropic.Anthropic", lambda: cliente)
    monkeypatch.setattr("jarvis.__main__.Hud", HudFalso)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("jarvis.conexion_ia._menu_conexion_ia", lambda: "api")
    entradas = iter(["hola", "salir"])
    monkeypatch.setattr("builtins.input", lambda _="": next(entradas))

    assert main(["--texto", "--hud"]) == 0
    assert estados == ["hablando", "escuchando", "pensando", "hablando", "escuchando",
                       "hablando", "cerrado"]


class _HudFalso:
    url = "http://127.0.0.1:0/"
    instancias = 0

    def __init__(self, *_args, **_kwargs):
        type(self).instancias += 1

    def estado(self, nombre, texto=None):
        pass

    def nivel(self, valor):
        pass

    def cerrar(self):
        pass


class _OidoFalso:
    es_dueño = True
    instancias_kwargs: list = []  # última construcción: qué kwargs recibió (para inspeccionar el wiring)

    def __init__(self, *_args, **_kwargs):
        self._frases = iter(["hola", "salir"])
        type(self).instancias_kwargs.append(_kwargs)

    def escuchar(self):
        return next(self._frases)


class _HablaFalsa:
    nombre = "falsa"
    interrumpible = False

    def decir(self, _texto):
        pass


def test_modo_completo_por_defecto_usa_voz_y_hud(monkeypatch, tmp_path):
    _HudFalso.instancias = 0
    cliente = ClienteFalso([NS(stop_reason="end_turn", content=[texto("Todo en orden, señor.")])])
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.setattr("jarvis.proveedores.anthropic_adaptador.anthropic.Anthropic", lambda: cliente)
    monkeypatch.setattr("jarvis.__main__.Hud", _HudFalso)
    monkeypatch.setattr("jarvis.voz.oido.Oido", _OidoFalso)
    monkeypatch.setattr("jarvis.voz.habla.crear_habla", lambda _config: _HablaFalsa())
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("jarvis.conexion_ia._menu_conexion_ia", lambda: "api")

    assert main([]) == 0
    assert _HudFalso.instancias == 1  # el HUD se abre solo, sin pasar --hud


def test_usa_ventana_nativa_si_esta_disponible_en_macos(monkeypatch, tmp_path):
    cliente = ClienteFalso([NS(stop_reason="end_turn", content=[texto("Todo en orden, señor.")])])
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.setattr("jarvis.proveedores.anthropic_adaptador.anthropic.Anthropic", lambda: cliente)
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("jarvis.hud.ventana_macos.disponible", lambda: True)
    monkeypatch.setattr("jarvis.__main__.Hud", _HudFalso)
    monkeypatch.setattr("jarvis.voz.oido.Oido", _OidoFalso)
    monkeypatch.setattr("jarvis.voz.habla.crear_habla", lambda _config: _HablaFalsa())
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("jarvis.conexion_ia._menu_conexion_ia", lambda: "api")

    llamadas = []

    def ejecutar_con_ventana_flotante_falso(url, trabajo):
        llamadas.append(url)
        trabajo()  # sin hilo ni NSApp.run(): corre el bucle directo, en el mismo hilo

    monkeypatch.setattr(
        "jarvis.hud.ventana_macos.ejecutar_con_ventana_flotante", ejecutar_con_ventana_flotante_falso
    )

    assert main([]) == 0
    assert len(llamadas) == 1 and llamadas[0] == _HudFalso.url


def test_ventana_nativa_conecta_ocultar_y_mostrar_a_oido(monkeypatch, tmp_path):
    """El modo de escucha pasiva (dormir_jarvis) debe poder ocultar/mostrar
    la ventana nativa: _ejecutar tiene que pasarle a Oido las funciones
    reales de ventana_macos, no dejarlas en el no-op por defecto."""
    cliente = ClienteFalso([NS(stop_reason="end_turn", content=[texto("Todo en orden, señor.")])])
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.setattr("jarvis.proveedores.anthropic_adaptador.anthropic.Anthropic", lambda: cliente)
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("jarvis.hud.ventana_macos.disponible", lambda: True)
    monkeypatch.setattr("jarvis.__main__.Hud", _HudFalso)
    _OidoFalso.instancias_kwargs = []
    monkeypatch.setattr("jarvis.voz.oido.Oido", _OidoFalso)
    monkeypatch.setattr("jarvis.voz.habla.crear_habla", lambda _config: _HablaFalsa())
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("jarvis.conexion_ia._menu_conexion_ia", lambda: "api")
    monkeypatch.setattr(
        "jarvis.hud.ventana_macos.ejecutar_con_ventana_flotante",
        lambda _url, trabajo: trabajo(),
    )

    assert main([]) == 0
    assert len(_OidoFalso.instancias_kwargs) == 1
    kwargs = _OidoFalso.instancias_kwargs[0]
    assert kwargs["al_dormir"].__module__.endswith("ventana_macos")
    assert kwargs["al_dormir"].__name__ == "ocultar_ventana"
    assert kwargs["al_despertar"].__name__ == "mostrar_ventana"


def test_sin_hud_mantiene_modo_voz(monkeypatch, tmp_path):
    _HudFalso.instancias = 0
    cliente = ClienteFalso([NS(stop_reason="end_turn", content=[texto("Todo en orden, señor.")])])
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.setattr("jarvis.proveedores.anthropic_adaptador.anthropic.Anthropic", lambda: cliente)
    monkeypatch.setattr("jarvis.__main__.Hud", _HudFalso)
    monkeypatch.setattr("jarvis.voz.oido.Oido", _OidoFalso)
    monkeypatch.setattr("jarvis.voz.habla.crear_habla", lambda _config: _HablaFalsa())
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("jarvis.conexion_ia._menu_conexion_ia", lambda: "api")

    assert main(["--sin-hud"]) == 0
    assert _HudFalso.instancias == 0  # --sin-hud no abre el HUD, pero la voz sigue activa


def test_bucle_conversacion_acepta_oido_y_habla_inyectados(tmp_path):
    """_bucle_conversacion tiene su propio seam para oido/habla: si se los
    pasan ya construidos, no crea un Oido/Habla real (no hace falta
    monkeypatchear jarvis.voz.oido.Oido ni jarvis.voz.habla.crear_habla)."""
    from jarvis.__main__ import _bucle_conversacion

    config = Config(carpeta_datos=tmp_path)
    args = NS(texto=False, pulsar=False, silencio=False)
    herramientas = Herramientas(tmp_path)
    cerebro = NS(herramientas=herramientas, responder=lambda texto, es_dueño: "Todo en orden, señor.")
    oido, habla = _OidoFalso(), _HablaFalsa()

    assert _bucle_conversacion(args, config, cerebro, _HudFalso(), oido=oido, habla=habla) == 0


def test_dormir_pedido_hace_que_el_bucle_llame_a_oido_dormir(tmp_path):
    """Integración real: la herramienta "dormir_jarvis" (ejecutada de
    verdad, no simulada) deja dormir_pedido=True en Herramientas;
    _bucle_conversacion debe notarlo y llamar oido.dormir(), y resetear
    el flag para no repetirlo en el turno siguiente."""
    from jarvis.__main__ import _bucle_conversacion

    config = Config(carpeta_datos=tmp_path)
    args = NS(texto=False, pulsar=False, silencio=False)
    herramientas = Herramientas(tmp_path)

    def responder_falso(_texto, es_dueño):
        herramientas.ejecutar("dormir_jarvis", {})  # como si el modelo hubiera llamado la herramienta
        return "Entrando en modo de escucha pasiva."

    cerebro = NS(herramientas=herramientas, responder=responder_falso)

    class _OidoQueCuentaDormir(_OidoFalso):
        def __init__(self):
            super().__init__()
            self.dormido = False

        def dormir(self):
            self.dormido = True

    oido = _OidoQueCuentaDormir()

    assert _bucle_conversacion(args, config, cerebro, _HudFalso(), oido=oido, habla=_HablaFalsa()) == 0
    assert oido.dormido is True
    assert herramientas.dormir_pedido is False


# --- modo suscripción (Claude Agent SDK) -------------------------------------

class ClienteSDKFalso:
    """Imita ClaudeSDKClient: query() + receive_response()."""

    def __init__(self, mensajes):
        self.mensajes = mensajes
        self.consultas = []

    async def query(self, texto):
        self.consultas.append(texto)

    async def receive_response(self):
        for m in self.mensajes:
            yield m

    async def disconnect(self):
        pass


def _resultado(texto, error=False):
    from claude_agent_sdk import ResultMessage
    return ResultMessage(subtype="error_during_execution" if error else "success",
                         duration_ms=1, duration_api_ms=1, is_error=error, num_turns=1,
                         session_id="s", result=texto)


def test_suscripcion_responde(herramientas):
    pytest.importorskip("claude_agent_sdk")
    from claude_agent_sdk import AssistantMessage, TextBlock
    from jarvis.cerebro_suscripcion import CerebroSuscripcion

    cliente = ClienteSDKFalso([
        AssistantMessage(content=[TextBlock(text="Son 42, señor.")], model="m"),
        _resultado("Son 42, señor."),
    ])
    cerebro = CerebroSuscripcion(Config(), herramientas, cliente)
    assert cerebro.responder("¿6 por 7?") == "Son 42, señor."
    assert cliente.consultas == ["¿6 por 7?"]
    cerebro.cerrar()


def test_suscripcion_responder_acepta_es_dueño_igual_que_cerebro_normal(herramientas):
    """CerebroSuscripcion.responder debe aceptar el mismo segundo argumento
    que Cerebro.responder (ver jarvis.cerebro): __main__._bucle_conversacion
    llama cerebro.responder(texto, es_dueño) sin saber cuál de las dos
    implementaciones está activa. Si las firmas no coinciden, el motor de
    suscripción crashea en voz, y además deja el gate de requiere_dueño
    (ver herramientas.py) siempre en True sin que nadie lo note."""
    pytest.importorskip("claude_agent_sdk")
    from jarvis.cerebro_suscripcion import CerebroSuscripcion

    cliente = ClienteSDKFalso([_resultado("ok")])
    cerebro = CerebroSuscripcion(Config(), herramientas, cliente)
    cerebro.responder("abrí Safari", False)
    assert herramientas.es_dueño_quien_habla is False
    cerebro.cerrar()


def test_suscripcion_error(herramientas):
    pytest.importorskip("claude_agent_sdk")
    from jarvis.cerebro_suscripcion import CerebroSuscripcion

    cerebro = CerebroSuscripcion(Config(), herramientas, ClienteSDKFalso([_resultado(None, True)]))
    assert "ha fallado" in cerebro.responder("hola")
    cerebro.cerrar()


def test_suscripcion_herramientas_mcp(herramientas):
    pytest.importorskip("claude_agent_sdk")
    import asyncio
    from jarvis.cerebro_suscripcion import _herramientas_sdk, _servidor_mcp

    assert _servidor_mcp(herramientas)["type"] == "sdk"
    calc = next(t for t in _herramientas_sdk(herramientas) if t.name == "calcular")
    salida = asyncio.run(calc.handler({"expresion": "6*7"}))
    assert salida == {"content": [{"type": "text", "text": "42"}], "is_error": False}


def test_menu_siempre_corre_incluso_con_todo_configurado(monkeypatch, tmp_path):
    """Ya no hay modo "auto" que salte el menú porque hay JARVIS_PROVEEDOR,
    una API key o una sesión detectada: el menú corre siempre."""
    from jarvis.conexion_ia import _crear_cerebro
    from jarvis.cerebro_suscripcion import CerebroSuscripcion

    pytest.importorskip("claude_agent_sdk")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ya-configurada")
    monkeypatch.setenv("JARVIS_PROVEEDOR", "anthropic")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_claude", lambda: True)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    entradas = iter(["2", "2"])  # proveedor en la nube -> Anthropic (ya logueado)
    monkeypatch.setattr("builtins.input", lambda _="": next(entradas))

    cerebro = _crear_cerebro(Config(carpeta_datos=tmp_path))

    assert isinstance(cerebro, CerebroSuscripcion)
    cerebro.cerrar()


def test_crear_cerebro_guardar_nombre_se_ve_en_el_cerebro_de_la_misma_sesion(monkeypatch, tmp_path):
    """Bug real confirmado en vivo: Herramientas se construía con el config
    de ANTES del menú; Cerebro recibía uno NUEVO (Config.desde_entorno(),
    después del menú) — dos objetos distintos. guardar_nombre mutaba el
    viejo, que Cerebro ya no veía: quedaba bien guardado en .env, pero
    Jarvis seguía despidiéndose con el nombre anterior en esa misma
    sesión, hasta reiniciar el proceso."""
    from jarvis.conexion_ia import _crear_cerebro

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("jarvis.conexion_ia._menu_conexion_ia", lambda: "api")
    monkeypatch.setattr("jarvis.config._RUTA_ENV_POR_DEFECTO", tmp_path / ".env")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("JARVIS_PROVEEDOR", "anthropic")

    cerebro = _crear_cerebro(Config(carpeta_datos=tmp_path))
    cerebro.herramientas.nuevo_turno("llamame Pedro")
    cerebro.herramientas.ejecutar("guardar_nombre", {"nombre": "Pedro"})

    assert cerebro.config.nombre_usuario == "Pedro"


def test_sin_tty_no_puede_mostrar_el_menu(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _crear_cerebro

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    with pytest.raises(RuntimeError, match="terminal interactiva"):
        _crear_cerebro(Config(carpeta_datos=tmp_path))


def test_menu_conexion_opcion_nube_pide_sub_menu_proveedor(monkeypatch, tmp_path):
    """Nivel 1 del menú: local o proveedor. Elegir proveedor abre el nivel 2."""
    from jarvis.conexion_ia import _menu_conexion_ia

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _="": "2")
    llamado = {}
    monkeypatch.setattr(
        "jarvis.conexion_ia._menu_proveedor_nube", lambda: llamado.setdefault("si", True) and "codex"
    )

    assert _menu_conexion_ia() == "codex"
    assert llamado == {"si": True}


def test_menu_conexion_opcion_invalida_en_nivel_uno_falla(monkeypatch):
    from jarvis.conexion_ia import _menu_conexion_ia

    monkeypatch.setattr("builtins.input", lambda _="": "9")

    with pytest.raises(RuntimeError, match="No encuentro"):
        _menu_conexion_ia()


def test_menu_proveedor_nube_opcion_anthropic_persiste_motor_sin_clave(monkeypatch, tmp_path):
    """Claude se conecta con la sesión de Claude Code: el menú no pide ni
    guarda ninguna clave, solo el motor elegido."""
    from jarvis.conexion_ia import _menu_proveedor_nube

    monkeypatch.setattr("jarvis.config._RUTA_ENV_POR_DEFECTO", tmp_path / ".env")
    monkeypatch.setattr("builtins.input", lambda _="": "2")
    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_claude", lambda: True)

    assert _menu_proveedor_nube() == "suscripcion"
    assert os.environ["JARVIS_MOTOR"] == "suscripcion"
    env = (tmp_path / ".env").read_text()
    assert "JARVIS_MOTOR=suscripcion" in env
    assert "ANTHROPIC_API_KEY" not in env


def test_menu_proveedor_nube_opcion_openai_persiste_proveedor_sin_clave(monkeypatch, tmp_path):
    """Codex habla directo contra el endpoint de Responses API con la
    sesión de Codex CLI: el menú no pide ni guarda ninguna clave, y no
    hace falta tener la CLI instalada (solo haber hecho codex login)."""
    from jarvis.conexion_ia import _menu_proveedor_nube

    monkeypatch.setattr("jarvis.config._RUTA_ENV_POR_DEFECTO", tmp_path / ".env")
    monkeypatch.setattr("builtins.input", lambda _="": "1")
    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_codex", lambda: True)

    assert _menu_proveedor_nube() == "codex"
    assert os.environ["JARVIS_MOTOR"] == "codex"
    env = (tmp_path / ".env").read_text()
    assert "JARVIS_MOTOR=codex" in env
    assert "JARVIS_PROVEEDOR" not in env
    assert "OPENAI_API_KEY" not in env and "sk-" not in env


def test_menu_proveedor_nube_opcion_invalida_falla(monkeypatch):
    from jarvis.conexion_ia import _menu_proveedor_nube

    monkeypatch.setattr("builtins.input", lambda _="": "9")

    with pytest.raises(RuntimeError, match="No encuentro"):
        _menu_proveedor_nube()


# --- login programático (Claude y Codex) -------------------------------------
#
# Nunca se dispara un login real en la test suite: subprocess.run se
# reemplaza siempre por un falso que no abre nada.


def test_configurar_claude_sin_sesion_dispara_login_y_verifica(monkeypatch):
    """Si no hay sesión, Jarvis lanza `claude` como subproceso (heredando
    stdin/stdout/stderr, por eso no se pasa capture_output), espera a que
    termine y recién ahí vuelve a chequear la sesión."""
    from jarvis.conexion_ia import _configurar_claude

    estado = {"logueado": False}
    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_claude", lambda: estado["logueado"])
    llamadas = []

    def login_falso(cmd, **kwargs):
        llamadas.append(cmd)
        estado["logueado"] = True  # simula que el usuario completó /login
        return NS(returncode=0)

    monkeypatch.setattr("jarvis.conexion_ia.subprocess.run", login_falso)

    assert _configurar_claude() == "suscripcion"
    assert llamadas == [["claude"]]
    assert os.environ["JARVIS_MOTOR"] == "suscripcion"


def test_configurar_claude_ya_logueado_no_dispara_login(monkeypatch):
    from jarvis.conexion_ia import _configurar_claude

    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_claude", lambda: True)

    def login_que_no_debe_llamarse(*_a, **_kw):
        pytest.fail("no debería intentar loguear si ya hay sesión")

    monkeypatch.setattr("jarvis.conexion_ia.subprocess.run", login_que_no_debe_llamarse)

    assert _configurar_claude() == "suscripcion"


def test_configurar_claude_login_no_deja_sesion_activa_falla(monkeypatch):
    from jarvis.conexion_ia import _configurar_claude

    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_claude", lambda: False)
    monkeypatch.setattr("jarvis.conexion_ia.subprocess.run", lambda *_a, **_kw: NS(returncode=0))

    with pytest.raises(RuntimeError, match="sesión activa"):
        _configurar_claude()


def test_configurar_claude_sin_cli_instalada_falla_con_mensaje_claro(monkeypatch):
    from jarvis.conexion_ia import _configurar_claude

    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_claude", lambda: False)

    def sin_binario(*_a, **_kw):
        raise OSError("no such file")

    monkeypatch.setattr("jarvis.conexion_ia.subprocess.run", sin_binario)

    with pytest.raises(RuntimeError, match="instalado"):
        _configurar_claude()


def test_configurar_codex_sin_sesion_dispara_login_y_verifica(monkeypatch):
    """`codex login` es un subcomando directo (confirmado con
    `codex --help`): se lanza igual heredando stdin/stdout/stderr."""
    from jarvis.conexion_ia import _configurar_codex

    estado = {"logueado": False}
    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_codex", lambda: estado["logueado"])
    llamadas = []

    def login_falso(cmd, **kwargs):
        llamadas.append(cmd)
        estado["logueado"] = True
        return NS(returncode=0)

    monkeypatch.setattr("jarvis.conexion_ia.subprocess.run", login_falso)

    assert _configurar_codex() == "codex"
    assert llamadas == [["codex", "login"]]
    assert os.environ["JARVIS_MOTOR"] == "codex"


def test_configurar_codex_ya_logueado_no_dispara_login(monkeypatch):
    from jarvis.conexion_ia import _configurar_codex

    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_codex", lambda: True)

    def login_que_no_debe_llamarse(*_a, **_kw):
        pytest.fail("no debería intentar loguear si ya hay sesión")

    monkeypatch.setattr("jarvis.conexion_ia.subprocess.run", login_que_no_debe_llamarse)

    assert _configurar_codex() == "codex"


def test_configurar_codex_login_no_deja_sesion_activa_falla(monkeypatch):
    from jarvis.conexion_ia import _configurar_codex

    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_codex", lambda: False)
    monkeypatch.setattr("jarvis.conexion_ia.subprocess.run", lambda *_a, **_kw: NS(returncode=1))

    with pytest.raises(RuntimeError, match="sesión activa"):
        _configurar_codex()


def test_configurar_codex_sin_cli_instalada_falla_con_mensaje_claro(monkeypatch):
    from jarvis.conexion_ia import _configurar_codex

    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_codex", lambda: False)

    def sin_binario(*_a, **_kw):
        raise OSError("no such file")

    monkeypatch.setattr("jarvis.conexion_ia.subprocess.run", sin_binario)

    with pytest.raises(RuntimeError, match="instalado"):
        _configurar_codex()


def test_menu_conexion_opcion_local_lista_y_persiste_modelo(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _menu_conexion_ia

    monkeypatch.setattr("jarvis.config._RUTA_ENV_POR_DEFECTO", tmp_path / ".env")
    monkeypatch.setattr("jarvis.conexion_ia.listar_modelos_ollama", lambda: ["qwen3:8b", "qwen3-vl:4b"])
    entradas = iter(["1", "1"])  # 1) modelo local -> 1) qwen3:8b
    monkeypatch.setattr("builtins.input", lambda _="": next(entradas))

    assert _menu_conexion_ia() == "api"
    assert os.environ["JARVIS_PROVEEDOR"] == "ollama"
    assert os.environ["JARVIS_MODELO"] == "qwen3:8b"
    env = (tmp_path / ".env").read_text()
    assert "JARVIS_PROVEEDOR=ollama" in env
    assert "JARVIS_MODELO=qwen3:8b" in env


def test_menu_conexion_opcion_local_sin_ollama_corriendo_no_crashea(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _menu_conexion_ia

    monkeypatch.chdir(tmp_path)

    def _listar_falla():
        raise OSError("conexión rechazada")

    monkeypatch.setattr("jarvis.conexion_ia.listar_modelos_ollama", _listar_falla)
    monkeypatch.setattr("builtins.input", lambda _="": "1")

    with pytest.raises(RuntimeError, match="Ollama"):
        _menu_conexion_ia()


def test_menu_conexion_opcion_local_sin_modelos_instalados(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _menu_conexion_ia

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("jarvis.conexion_ia.listar_modelos_ollama", lambda: [])
    monkeypatch.setattr("builtins.input", lambda _="": "1")

    with pytest.raises(RuntimeError, match="modelos instalados"):
        _menu_conexion_ia()


def test_menu_conexion_opcion_invalida_falla(monkeypatch):
    from jarvis.conexion_ia import _menu_conexion_ia

    monkeypatch.setattr("builtins.input", lambda _="": "9")

    with pytest.raises(RuntimeError, match="No encuentro"):
        _menu_conexion_ia()


# --- menú en ventana (sin terminal, ej. ícono de escritorio) -----------------
#
# Nunca se abre una ventana real en la suite: se mockea
# ``ventana_macos.ejecutar_ventana_menu`` para que corra ``trabajo`` directo,
# igual que ya se hace con ``ejecutar_con_ventana_flotante`` para el HUD.


def test_crear_cerebro_sin_tty_y_sin_ventana_falla_con_mensaje_claro(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _crear_cerebro

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("jarvis.conexion_ia._hud_ventana_disponible", lambda: False)

    with pytest.raises(RuntimeError, match="terminal interactiva"):
        _crear_cerebro(Config(carpeta_datos=tmp_path))


def test_crear_cerebro_sin_tty_y_con_ventana_usa_el_menu_de_ventana(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _crear_cerebro

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("jarvis.conexion_ia._hud_ventana_disponible", lambda: True)
    monkeypatch.setattr("jarvis.conexion_ia._menu_conexion_ia_ventana", lambda: "api")
    monkeypatch.setenv("JARVIS_PROVEEDOR", "ollama")
    monkeypatch.setenv("JARVIS_MODELO", "qwen3:8b")

    cerebro = _crear_cerebro(Config(carpeta_datos=tmp_path))

    from jarvis.proveedores import AdaptadorOllama
    assert isinstance(cerebro.proveedor, AdaptadorOllama)


class _ServidorMenuFalso:
    """Imita ``ServidorMenu`` sin levantar ningún servidor HTTP real: una
    cola de acciones que el test alimenta a mano, y un registro de los
    estados que se le fueron pidiendo mostrar."""

    def __init__(self, acciones):
        self.url = "http://127.0.0.1:0/"
        self._acciones = iter(acciones)
        self.estados: list[dict] = []
        self.cerrado = False

    def actualizar(self, **cambios):
        self.estados.append(cambios)

    def esperar_accion(self, timeout=None):
        return next(self._acciones, None)

    def cerrar(self):
        self.cerrado = True


def _correr_ventana_falsa(monkeypatch, servidor_falso):
    monkeypatch.setattr("jarvis.hud.servidor_menu.ServidorMenu", lambda: servidor_falso)

    def ejecutar_ventana_menu_falso(_url, trabajo):
        trabajo()

    monkeypatch.setattr("jarvis.hud.ventana_macos.ejecutar_ventana_menu", ejecutar_ventana_menu_falso)


def test_menu_ventana_camino_local_elige_y_persiste_modelo(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _menu_conexion_ia_ventana

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("jarvis.conexion_ia.listar_modelos_ollama", lambda: ["qwen3:8b", "qwen3-vl:4b"])
    servidor = _ServidorMenuFalso([{"tipo": "local"}, {"tipo": "modelo", "modelo": "qwen3:8b"}])
    _correr_ventana_falsa(monkeypatch, servidor)

    assert _menu_conexion_ia_ventana() == "api"
    assert os.environ["JARVIS_PROVEEDOR"] == "ollama"
    assert os.environ["JARVIS_MODELO"] == "qwen3:8b"
    assert servidor.cerrado
    assert {"paso": "hecho", "mensaje": "Usando el modelo local qwen3:8b."} in servidor.estados


def test_menu_ventana_camino_local_sin_modelos_termina_en_error(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _menu_conexion_ia_ventana

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("jarvis.conexion_ia.listar_modelos_ollama", lambda: [])
    monkeypatch.setattr("jarvis.conexion_ia.time.sleep", lambda _s: None)
    servidor = _ServidorMenuFalso([{"tipo": "local"}])
    _correr_ventana_falsa(monkeypatch, servidor)

    with pytest.raises(RuntimeError, match="modelos instalados"):
        _menu_conexion_ia_ventana()
    assert servidor.cerrado


def test_menu_ventana_camino_proveedor_ya_logueado_no_abre_terminal(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _menu_conexion_ia_ventana

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_claude", lambda: True)

    def terminal_que_no_debe_abrirse(*_a, **_kw):
        pytest.fail("no debería abrir una Terminal si ya hay sesión")

    monkeypatch.setattr("jarvis.conexion_ia._abrir_terminal_con_comando", terminal_que_no_debe_abrirse)
    servidor = _ServidorMenuFalso([{"tipo": "proveedor"}, {"tipo": "anthropic"}])
    _correr_ventana_falsa(monkeypatch, servidor)

    assert _menu_conexion_ia_ventana() == "suscripcion"
    assert os.environ["JARVIS_MOTOR"] == "suscripcion"


def test_menu_ventana_camino_proveedor_sin_sesion_abre_terminal_y_pollea(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _menu_conexion_ia_ventana

    monkeypatch.chdir(tmp_path)
    estado = {"logueado": False}
    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_codex", lambda: estado["logueado"])
    llamadas = []

    def abrir_terminal_falso(comando):
        llamadas.append(comando)
        estado["logueado"] = True  # simula que el usuario terminó el login en la Terminal

    monkeypatch.setattr("jarvis.conexion_ia._abrir_terminal_con_comando", abrir_terminal_falso)
    monkeypatch.setattr("jarvis.conexion_ia.time.sleep", lambda _s: None)
    servidor = _ServidorMenuFalso([{"tipo": "proveedor"}, {"tipo": "openai"}])
    _correr_ventana_falsa(monkeypatch, servidor)

    assert _menu_conexion_ia_ventana() == "codex"
    assert llamadas == [["codex", "login"]]
    assert os.environ["JARVIS_MOTOR"] == "codex"


def test_menu_ventana_camino_proveedor_login_nunca_detectado_agota_tiempo(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _menu_conexion_ia_ventana

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("jarvis.conexion_ia._hay_sesion_claude", lambda: False)
    monkeypatch.setattr("jarvis.conexion_ia._abrir_terminal_con_comando", lambda _comando: None)
    monkeypatch.setattr("jarvis.conexion_ia.TIMEOUT_LOGIN_VENTANA_SEGUNDOS", 0)
    monkeypatch.setattr("jarvis.conexion_ia.time.sleep", lambda _s: None)
    servidor = _ServidorMenuFalso([{"tipo": "proveedor"}, {"tipo": "anthropic"}])
    _correr_ventana_falsa(monkeypatch, servidor)

    with pytest.raises(RuntimeError, match="No detecté una sesión activa"):
        _menu_conexion_ia_ventana()
    assert servidor.cerrado


def test_abrir_terminal_con_comando_usa_osascript_con_terminal_app(monkeypatch):
    from jarvis.conexion_ia import _abrir_terminal_con_comando

    llamadas = []
    monkeypatch.setattr(
        "jarvis.conexion_ia.subprocess.run",
        lambda cmd, **kwargs: llamadas.append((cmd, kwargs)) or NS(returncode=0),
    )

    _abrir_terminal_con_comando(["codex", "login"])

    (cmd, kwargs), = llamadas
    assert cmd[0] == "osascript"
    assert "Terminal" in cmd[-1]
    assert "codex login" in cmd[-1]
    assert kwargs.get("check") is True


def test_redirigir_log_no_hace_nada_fuera_del_bundle(tmp_path, monkeypatch):
    """Fuera del bundle (desarrollo, tests), sys.frozen no existe -> no debe
    tocar sys.stdout/stderr ni crear ningun archivo."""
    import sys as sys_real

    from jarvis.instancia import _redirigir_log_si_es_bundle_standalone

    stdout_original = sys_real.stdout
    stderr_original = sys_real.stderr
    _redirigir_log_si_es_bundle_standalone(tmp_path)

    assert sys_real.stdout is stdout_original
    assert sys_real.stderr is stderr_original
    assert not (tmp_path / "jarvis.log").exists()


def test_redirigir_log_escribe_al_archivo_dentro_del_bundle(tmp_path, monkeypatch):
    """Dentro del bundle (sys.frozen = True), stdout/stderr deben quedar
    apuntando a ~/.jarvis/jarvis.log -- sin esto, un error ahi quedaba
    invisible (justo el bug reportado: 'Jarvis abre un momento y se cierra',
    sin nada en ningun lado para diagnosticarlo)."""
    import sys as sys_real

    from jarvis.instancia import _redirigir_log_si_es_bundle_standalone

    monkeypatch.setattr(sys_real, "frozen", True, raising=False)
    stdout_original = sys_real.stdout
    stderr_original = sys_real.stderr
    try:
        _redirigir_log_si_es_bundle_standalone(tmp_path)
        print("mensaje de prueba")
        sys_real.stdout.flush()
        assert "mensaje de prueba" in (tmp_path / "jarvis.log").read_text()
    finally:
        sys_real.stdout.close()
        sys_real.stdout = stdout_original
        sys_real.stderr = stderr_original


def test_instancia_unica_primera_vez_toma_el_lock(tmp_path):
    from jarvis.instancia import _liberar_instancia, _tomar_instancia_unica

    assert _tomar_instancia_unica(tmp_path) is True
    assert (tmp_path / "jarvis.pid").is_file()
    _liberar_instancia(tmp_path)
    assert not (tmp_path / "jarvis.pid").exists()


def test_instancia_unica_rechaza_si_ya_hay_una_viva(tmp_path):
    import os

    from jarvis.instancia import _tomar_instancia_unica

    (tmp_path / "jarvis.pid").write_text(str(os.getpid()))  # este mismo proceso: siempre vivo

    assert _tomar_instancia_unica(tmp_path) is False


def test_instancia_unica_ignora_pid_de_proceso_muerto(tmp_path):
    from jarvis.instancia import _tomar_instancia_unica

    (tmp_path / "jarvis.pid").write_text("999999999")  # casi seguro no existe

    assert _tomar_instancia_unica(tmp_path) is True


def test_liberar_instancia_no_borra_el_pid_de_otra_instancia(tmp_path):
    from jarvis.instancia import _liberar_instancia

    (tmp_path / "jarvis.pid").write_text("1")  # pid ajeno

    _liberar_instancia(tmp_path)

    assert (tmp_path / "jarvis.pid").read_text() == "1"


def test_hay_sesion_claude_detecta_archivo_de_credenciales(monkeypatch, tmp_path):
    from jarvis.conexion_ia import _hay_sesion_claude

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert _hay_sesion_claude() is False

    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ".credentials.json").write_text("{}")
    assert _hay_sesion_claude() is True


def test_clave_del_menu_sigue_disponible_tras_el_cierre(monkeypatch, tmp_path):
    """A diferencia del comportamiento anterior (clave solo en memoria), el
    nuevo flujo persiste a propósito la elección del menú: no debe borrarse
    al cerrar Jarvis."""
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config_falsa = Config(carpeta_datos=tmp_path)

    def crear_cerebro_falso(_config, forzar_menu=False):
        os.environ["ANTHROPIC_API_KEY"] = "del-menu"  # lo que haría _configurar_proveedor_nube
        return NS(config=config_falsa, responder=lambda t: "ok")

    monkeypatch.setattr("jarvis.__main__._crear_cerebro", crear_cerebro_falso)
    monkeypatch.setattr("builtins.input", lambda _="": "salir")

    assert main(["--texto"]) == 0
    assert os.environ["ANTHROPIC_API_KEY"] == "del-menu"


def test_clave_preexistente_sigue_tras_el_cierre(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "real")
    config_falsa = Config(carpeta_datos=tmp_path)

    monkeypatch.setattr(
        "jarvis.__main__._crear_cerebro",
        lambda _config, forzar_menu=False: NS(config=config_falsa, responder=lambda t: "ok"),
    )
    monkeypatch.setattr("builtins.input", lambda _="": "salir")

    assert main(["--texto"]) == 0
    assert os.environ["ANTHROPIC_API_KEY"] == "real"


def _detectar(detector, volumenes):
    return [(i, e) for i, v in enumerate(volumenes) if (e := detector.procesar(v))]


def test_detector_voz_empieza_y_termina():
    from jarvis.voz.oido import DetectorVoz

    detector = DetectorVoz()
    ruido, voz = [0.002] * 50, [0.08] * 40
    eventos = _detectar(detector, ruido + voz + ruido)
    assert eventos == [(53, "inicio"), (116, "fin")]  # 4 bloques de voz para empezar, 27 de silencio para acabar


def test_detector_voz_ignora_golpes_cortos_y_se_adapta_al_ruido():
    from jarvis.voz.oido import DetectorVoz

    detector = DetectorVoz()
    assert _detectar(detector, [0.002] * 20 + [0.2, 0.2] + [0.002] * 20) == []  # un golpe no es voz
    # Habitación ruidosa: el umbral sube y ese ruido constante deja de contar como voz.
    detector = DetectorVoz()
    _detectar(detector, [0.004] * 200)
    assert detector.umbral > 0.01
    assert _detectar(detector, [0.0105] * 50) == []


def test_detector_voz_corta_frases_eternas():
    from jarvis.voz.oido import DetectorVoz

    detector = DetectorVoz(bloques_maximo=100)
    eventos = _detectar(detector, [0.1] * 200)
    assert [e for _, e in eventos][:2] == ["inicio", "fin"]


def test_palabra_activacion():
    from jarvis.voz.oido import filtrar_palabra_activacion as filtrar

    assert filtrar("¿Qué hora es?", "") == "¿Qué hora es?"
    assert filtrar("¿Qué hora es?", "jarvis") == ""
    assert filtrar("Jarvis, ¿qué hora es?", "jarvis") == "qué hora es"
    assert filtrar("Oye Yarvis apunta pan", "jarvis,yarvis") == "Oye apunta pan"
    assert filtrar("Jarvis.", "jarvis") == "Jarvis."


class _InputStreamFalso:
    instancia = None

    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        _InputStreamFalso.instancia = self

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _esperar_instancia_fake(timeout=2.0):
    import time as _time
    limite = _time.monotonic() + timeout
    while _InputStreamFalso.instancia is None and _time.monotonic() < limite:
        _time.sleep(0.01)
    return _InputStreamFalso.instancia


def test_vigilar_interrupcion_detecta_la_palabra(monkeypatch):
    import threading as _threading

    import numpy as np

    from jarvis.voz.oido import Oido

    _InputStreamFalso.instancia = None
    monkeypatch.setattr("sounddevice.InputStream", _InputStreamFalso)

    oido = Oido.__new__(Oido)
    oido.sensibilidad = 3.0
    oido._transcribir = lambda _audio: "jarvis, pará"

    detener_vigia = _threading.Event()
    llamado = []
    interrumpido = oido.vigilar_interrupcion("jarvis", detener_vigia, lambda: llamado.append(True))

    instancia = _esperar_instancia_fake()
    assert instancia is not None, "el hilo nunca abrió el InputStream"

    voz = np.full((480, 1), 0.2, dtype="float32")
    silencio = np.zeros((480, 1), dtype="float32")
    for _ in range(5):
        instancia.callback(voz, 480, None, None)
    for _ in range(30):
        instancia.callback(silencio, 480, None, None)

    assert interrumpido.wait(timeout=2)
    assert llamado == [True]
    detener_vigia.set()


def test_vigilar_interrupcion_se_cancela_sin_disparar(monkeypatch):
    import threading as _threading
    import time as _time

    from jarvis.voz.oido import Oido

    _InputStreamFalso.instancia = None
    monkeypatch.setattr("sounddevice.InputStream", _InputStreamFalso)

    oido = Oido.__new__(Oido)
    oido.sensibilidad = 3.0
    oido._transcribir = lambda _audio: "buen día"

    detener_vigia = _threading.Event()
    llamado = []
    interrumpido = oido.vigilar_interrupcion("jarvis", detener_vigia, lambda: llamado.append(True))

    assert _esperar_instancia_fake() is not None
    detener_vigia.set()
    _time.sleep(0.4)  # darle tiempo al hilo a salir del loop (timeout interno de 0.2s)

    assert not interrumpido.is_set()
    assert llamado == []


# --- Voz ---------------------------------------------------------------------

from jarvis.voz import habla as habla_mod


class MotorFalso:
    def __init__(self, nombre, falla=False):
        self.nombre, self.falla, self.dichos = nombre, falla, []

    def decir(self, texto):
        if self.falla:
            raise OSError("roto")
        self.dichos.append(texto)


def test_habla_cambia_de_motor_si_falla(capsys):
    roto, bueno = MotorFalso("piper", falla=True), MotorFalso("macos")
    habla = habla_mod.Habla([roto, bueno])
    habla.decir("**Hola**, señor")
    habla.decir("Sigo aquí")
    assert bueno.dichos == ["Hola, señor", "Sigo aquí"]
    assert habla.nombre == "macos"
    assert "sigo con macos" in capsys.readouterr().err


def test_habla_sin_motores_no_rompe():
    habla = habla_mod.Habla([MotorFalso("piper", falla=True)])
    habla.decir("hola")
    habla.decir("hola otra vez")


class MotorFalsoInterrumpible(MotorFalso):
    def __init__(self, nombre):
        super().__init__(nombre)
        self.detenido = False

    def detener(self):
        self.detenido = True


def test_habla_interrumpible_segun_motor():
    assert habla_mod.Habla([MotorFalso("macos")]).interrumpible is False
    assert habla_mod.Habla([MotorFalsoInterrumpible("kokoro")]).interrumpible is True


def test_habla_detener_delega_al_motor_si_corresponde():
    motor = MotorFalsoInterrumpible("kokoro")
    habla_mod.Habla([motor]).detener()
    assert motor.detenido is True


def test_habla_detener_no_rompe_si_motor_no_soporta():
    habla_mod.Habla([MotorFalso("macos")]).detener()  # no debe lanzar


@pytest.mark.parametrize("Motor,atributos", [
    (habla_mod.MotorKokoro, {}),
    (habla_mod.MotorPiper, {}),
    (habla_mod.MotorElevenLabs, {}),
])
def test_motores_sd_play_tienen_detener(Motor, atributos):
    """Los tres motores que reproducen con sd.play() deben poder cortarse."""
    motor = Motor.__new__(Motor)
    llamadas = []
    motor.sd = NS(stop=lambda: llamadas.append("detenido"))
    motor.detener()
    assert llamadas == ["detenido"]


def test_elegir_voz_macos_prefiere_jorge_premium():
    salida = (
        "Albert              en_US    # Hello! My name is Albert.\n"
        "Jorge               es_ES    # ¡Hola! Me llamo Jorge.\n"
        "Jorge (Premium)     es_ES    # ¡Hola! Me llamo Jorge.\n"
        "Mónica              es_ES    # ¡Hola! Me llamo Mónica.\n"
    )
    voces = habla_mod.analizar_voces_macos(salida)
    assert ("Jorge (Premium)", "es_ES") in voces
    assert habla_mod.elegir_voz_macos(voces, "es") == "Jorge (Premium)"
    assert habla_mod.elegir_voz_macos([("Mónica", "es_ES")], "es") == "Mónica"
    assert habla_mod.elegir_voz_macos([("Albert", "en_US")], "es") == ""


def test_quitar_clics_alisa_salto_brusco():
    import numpy as np

    audio = np.zeros(1000, dtype=np.float32)
    audio[500] = 0.9  # salto puntual artificial, como el que produce Kokoro

    resultado = habla_mod._quitar_clics(audio, np, frecuencia=24000)

    assert np.max(np.abs(np.diff(resultado))) < 0.3
    assert np.array_equal(resultado[:420], audio[:420])  # fuera de la ventana, intacto
    assert np.array_equal(resultado[580:], audio[580:])


def test_quitar_clics_no_toca_audio_limpio():
    import numpy as np

    audio = np.sin(np.linspace(0, 20, 1000)).astype(np.float32) * 0.3
    resultado = habla_mod._quitar_clics(audio, np, frecuencia=24000)

    assert np.array_equal(resultado, audio)


def test_crear_habla_elige_motor(monkeypatch, tmp_path):
    creados = []

    def crear(nombre, config, explicito):
        creados.append(nombre)
        return MotorFalso(nombre) if nombre in ("macos", "pyttsx3") else None

    monkeypatch.setattr(habla_mod, "_crear_motor", crear)
    assert habla_mod.crear_habla(Config(carpeta_datos=tmp_path)).nombre == "macos"
    assert habla_mod.crear_habla(Config(carpeta_datos=tmp_path, motor_voz="pyttsx3")).nombre == "pyttsx3"
    with pytest.raises(RuntimeError):
        habla_mod.crear_habla(Config(carpeta_datos=tmp_path, motor_voz="hal9000"))


def test_elevenlabs_sin_clave_se_omite(tmp_path):
    config = Config(carpeta_datos=tmp_path)
    assert habla_mod._crear_motor("elevenlabs", config, explicito=False) is None
    with pytest.raises(RuntimeError):
        habla_mod._crear_motor("elevenlabs", config, explicito=True)
