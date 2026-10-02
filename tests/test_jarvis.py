"""Pruebas sin red: se sustituye el cliente de Claude por uno falso."""

import os
import stat
import sys
from types import SimpleNamespace as NS

import pytest

from jarvis.__main__ import main
from jarvis.cerebro import Cerebro
from jarvis.config import Config
from jarvis.herramientas import Herramientas, evaluar_expresion


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
    cerebro = Cerebro(Config(), herramientas, cliente)

    assert cerebro.responder("¿Cuánto es 6 por 7?") == "Son 42, señor."
    resultado = cerebro.historial[2]["content"][0]
    assert resultado["type"] == "tool_result" and resultado["content"] == "42"
    assert cliente.peticiones[0]["model"] == "claude-opus-5-5"


def test_cerebro_rechazo(herramientas):
    cliente = ClienteFalso([NS(stop_reason="refusal", content=[])])
    assert "no puedo" in Cerebro(Config(), herramientas, cliente).responder("algo").lower()


def test_modo_texto_de_principio_a_fin(monkeypatch, tmp_path, capsys):
    cliente = ClienteFalso([NS(stop_reason="end_turn", content=[texto("Todo en orden, señor.")])])
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.setattr("jarvis.cerebro.anthropic.Anthropic", lambda: cliente)
    entradas = iter(["hola", "salir"])
    monkeypatch.setattr("builtins.input", lambda _="": next(entradas))

    assert main(["--texto"]) == 0
    salida = capsys.readouterr().out
    assert "JARVIS: Todo en orden, señor." in salida
    assert "Hasta luego" in salida


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
    monkeypatch.setattr("jarvis.cerebro.anthropic.Anthropic", lambda: cliente)
    monkeypatch.setattr("jarvis.__main__.Hud", HudFalso)
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
    def __init__(self, *_args, **_kwargs):
        self._frases = iter(["hola", "salir"])

    def escuchar(self):
        return next(self._frases)


class _HablaFalsa:
    nombre = "falsa"

    def decir(self, _texto):
        pass


def test_modo_completo_por_defecto_usa_voz_y_hud(monkeypatch, tmp_path):
    _HudFalso.instancias = 0
    cliente = ClienteFalso([NS(stop_reason="end_turn", content=[texto("Todo en orden, señor.")])])
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.setattr("jarvis.cerebro.anthropic.Anthropic", lambda: cliente)
    monkeypatch.setattr("jarvis.__main__.Hud", _HudFalso)
    monkeypatch.setattr("jarvis.voz.oido.Oido", _OidoFalso)
    monkeypatch.setattr("jarvis.voz.habla.crear_habla", lambda _config: _HablaFalsa())

    assert main([]) == 0
    assert _HudFalso.instancias == 1  # el HUD se abre solo, sin pasar --hud


def test_sin_hud_mantiene_modo_voz(monkeypatch, tmp_path):
    _HudFalso.instancias = 0
    cliente = ClienteFalso([NS(stop_reason="end_turn", content=[texto("Todo en orden, señor.")])])
    monkeypatch.setenv("JARVIS_CARPETA_DATOS", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.setattr("jarvis.cerebro.anthropic.Anthropic", lambda: cliente)
    monkeypatch.setattr("jarvis.__main__.Hud", _HudFalso)
    monkeypatch.setattr("jarvis.voz.oido.Oido", _OidoFalso)
    monkeypatch.setattr("jarvis.voz.habla.crear_habla", lambda _config: _HablaFalsa())

    assert main(["--sin-hud"]) == 0
    assert _HudFalso.instancias == 0  # --sin-hud no abre el HUD, pero la voz sigue activa


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


def test_auto_sin_clave_usa_suscripcion(monkeypatch, tmp_path):
    pytest.importorskip("claude_agent_sdk")
    from jarvis.__main__ import _crear_cerebro
    from jarvis.cerebro_suscripcion import CerebroSuscripcion

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("jarvis.__main__._hay_sesion_claude", lambda: True)
    cerebro = _crear_cerebro(Config(carpeta_datos=tmp_path))
    assert isinstance(cerebro, CerebroSuscripcion)
    cerebro.cerrar()


def test_auto_sin_clave_ni_sesion_pide_menu(monkeypatch, tmp_path):
    from jarvis.__main__ import _crear_cerebro

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setattr("jarvis.__main__._hay_sesion_claude", lambda: False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    with pytest.raises(RuntimeError, match="No encuentro"):
        _crear_cerebro(Config(carpeta_datos=tmp_path))


def test_menu_activacion_opcion_api_guarda_env(monkeypatch, tmp_path):
    from jarvis.__main__ import _menu_activacion

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setattr("getpass.getpass", lambda _: "sk-ant-prueba")

    assert _menu_activacion() == "api"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-prueba"
    assert "ANTHROPIC_API_KEY=sk-ant-prueba" in (tmp_path / ".env").read_text()


def test_menu_activacion_opcion_api_sin_clave_falla(monkeypatch, tmp_path):
    from jarvis.__main__ import _menu_activacion

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _: "1")
    monkeypatch.setattr("getpass.getpass", lambda _: "")

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        _menu_activacion()


def test_menu_activacion_opcion_suscripcion_sin_sesion(monkeypatch):
    from jarvis.__main__ import _menu_activacion

    monkeypatch.setattr("builtins.input", lambda _: "2")
    monkeypatch.setattr("jarvis.__main__._hay_sesion_claude", lambda: False)

    with pytest.raises(RuntimeError, match="sesión"):
        _menu_activacion()


def test_menu_activacion_opcion_suscripcion_con_sesion(monkeypatch):
    from jarvis.__main__ import _menu_activacion

    monkeypatch.setattr("builtins.input", lambda _: "2")
    monkeypatch.setattr("jarvis.__main__._hay_sesion_claude", lambda: True)

    assert _menu_activacion() == "suscripcion"


def test_menu_activacion_opcion_invalida_falla(monkeypatch):
    from jarvis.__main__ import _menu_activacion

    monkeypatch.setattr("builtins.input", lambda _: "3")

    with pytest.raises(RuntimeError, match="No encuentro"):
        _menu_activacion()


def test_hay_sesion_claude_detecta_archivo_de_credenciales(monkeypatch, tmp_path):
    from jarvis.__main__ import _hay_sesion_claude

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert _hay_sesion_claude() is False

    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ".credentials.json").write_text("{}")
    assert _hay_sesion_claude() is True


def test_guardar_en_env_reemplaza_sin_duplicar(tmp_path):
    from jarvis.__main__ import _guardar_en_env

    ruta = tmp_path / ".env"
    ruta.write_text("ANTHROPIC_API_KEY=vieja\nJARVIS_IDIOMA=es\n", encoding="utf-8")

    _guardar_en_env("ANTHROPIC_API_KEY", "nueva", ruta)

    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert lineas == ["ANTHROPIC_API_KEY=nueva", "JARVIS_IDIOMA=es"]


@pytest.mark.skipif(sys.platform == "win32", reason="permisos unix, no aplica en Windows")
def test_guardar_en_env_restringe_permisos(tmp_path):
    from jarvis.__main__ import _guardar_en_env

    ruta = tmp_path / ".env"
    ruta.write_text("ANTHROPIC_API_KEY=vieja\n", encoding="utf-8")
    ruta.chmod(0o644)  # simula un .env con permisos abiertos

    _guardar_en_env("ANTHROPIC_API_KEY", "nueva", ruta)

    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600


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
