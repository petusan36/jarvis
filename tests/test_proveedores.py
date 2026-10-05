"""Pruebas de los adaptadores de IA (puerto ProveedorIA): todas sin red real,
mockeando el SDK/HTTP de cada proveedor."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from jarvis.proveedores import (
    AdaptadorAnthropic,
    AdaptadorOllama,
    AdaptadorOpenAI,
    BloqueTexto,
    BloqueUsoHerramienta,
    ResultadoHerramienta,
    TurnoAsistente,
    TurnoResultadoHerramienta,
    TurnoUsuario,
    listar_modelos_ollama,
)
from jarvis.proveedores._comun import herramienta_a_function_calling

HERRAMIENTAS = [
    {
        "name": "calcular",
        "description": "Evalúa una expresión matemática.",
        "input_schema": {
            "type": "object",
            "properties": {"expresion": {"type": "string"}},
            "required": ["expresion"],
            "additionalProperties": False,
        },
        "strict": True,
    }
]


def _kwargs_comunes():
    return dict(
        mensajes=[TurnoUsuario(texto="¿Cuánto es 6 por 7?")],
        sistema="Sos Jarvis.",
        herramientas=HERRAMIENTAS,
        modelo="algun-modelo",
        max_tokens=100,
        esfuerzo="low",
    )


# --- helper compartido ------------------------------------------------------

def test_herramienta_a_function_calling_traduce_el_esquema():
    traducida = herramienta_a_function_calling(HERRAMIENTAS[0])
    assert traducida == {
        "type": "function",
        "function": {
            "name": "calcular",
            "description": "Evalúa una expresión matemática.",
            "parameters": HERRAMIENTAS[0]["input_schema"],
            "strict": True,
        },
    }


# --- AdaptadorAnthropic ------------------------------------------------------

class _ClienteAnthropicFalso:
    """Imita client.beta.messages.create devolviendo respuestas preparadas."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.peticiones = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.peticiones.append(kwargs)
        return self.respuestas.pop(0)


def test_adaptador_anthropic_respuesta_de_texto():
    cliente = _ClienteAnthropicFalso([
        NS(stop_reason="end_turn", content=[NS(type="text", text="Son 42, señor.")]),
    ])
    adaptador = AdaptadorAnthropic(cliente)

    respuesta = adaptador.responder(**_kwargs_comunes())

    assert respuesta.detenida_por == "texto"
    assert respuesta.contenido == [BloqueTexto(texto="Son 42, señor.")]
    peticion = cliente.peticiones[0]
    assert peticion["model"] == "algun-modelo" and peticion["system"] == "Sos Jarvis."
    assert peticion["messages"][0] == {"role": "user", "content": "¿Cuánto es 6 por 7?"}


def test_adaptador_anthropic_respuesta_con_herramienta():
    cliente = _ClienteAnthropicFalso([
        NS(stop_reason="tool_use", content=[NS(type="tool_use", id="t1", name="calcular", input={"expresion": "6*7"})]),
    ])
    respuesta = AdaptadorAnthropic(cliente).responder(**_kwargs_comunes())

    assert respuesta.detenida_por == "herramienta"
    assert respuesta.contenido == [BloqueUsoHerramienta(id="t1", nombre="calcular", entrada={"expresion": "6*7"})]


def test_adaptador_anthropic_reenvia_bruto_para_preservar_razonamiento():
    """El contenido crudo (con bloques que Cerebro no entiende, p. ej.
    razonamiento) debe reenviarse intacto en la vuelta siguiente."""
    bloque_razonamiento = NS(type="thinking", thinking="un secreto")
    bloque_texto = NS(type="text", text="ok")
    cliente = _ClienteAnthropicFalso([
        NS(stop_reason="end_turn", content=[bloque_razonamiento, bloque_texto]),
        NS(stop_reason="end_turn", content=[NS(type="text", text="segunda vuelta")]),
    ])
    adaptador = AdaptadorAnthropic(cliente)

    primera = adaptador.responder(**_kwargs_comunes())
    turno_asistente = TurnoAsistente(contenido=primera.contenido, bruto=primera.bruto)
    adaptador.responder(**{**_kwargs_comunes(), "mensajes": [TurnoUsuario(texto="hola"), turno_asistente]})

    mensajes_segunda_llamada = cliente.peticiones[1]["messages"]
    assert mensajes_segunda_llamada[1]["content"] == [bloque_razonamiento, bloque_texto]


# --- AdaptadorOpenAI ---------------------------------------------------------

class _ClienteOpenAIFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.peticiones = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.peticiones.append(kwargs)
        return self.respuestas.pop(0)


def _respuesta_openai(mensaje, finish_reason):
    return NS(choices=[NS(message=mensaje, finish_reason=finish_reason)])


def test_adaptador_openai_respuesta_de_texto():
    mensaje = NS(content="Son 42, señor.", tool_calls=None)
    cliente = _ClienteOpenAIFalso([_respuesta_openai(mensaje, "stop")])

    respuesta = AdaptadorOpenAI(cliente=cliente).responder(**_kwargs_comunes())

    assert respuesta.detenida_por == "texto"
    assert respuesta.contenido == [BloqueTexto(texto="Son 42, señor.")]
    peticion = cliente.peticiones[0]
    assert peticion["messages"][0] == {"role": "system", "content": "Sos Jarvis."}
    assert peticion["tools"][0]["function"]["name"] == "calcular"


def test_adaptador_openai_respuesta_con_herramienta_y_traduce_tools():
    llamada = NS(id="call_1", function=NS(name="calcular", arguments=json.dumps({"expresion": "6*7"})))
    mensaje = NS(content=None, tool_calls=[llamada])
    cliente = _ClienteOpenAIFalso([_respuesta_openai(mensaje, "tool_calls")])

    respuesta = AdaptadorOpenAI(cliente=cliente).responder(**_kwargs_comunes())

    assert respuesta.detenida_por == "herramienta"
    assert respuesta.contenido == [BloqueUsoHerramienta(id="call_1", nombre="calcular", entrada={"expresion": "6*7"})]


def test_adaptador_openai_longitud_y_resultado_de_herramienta_por_mensaje():
    mensaje = NS(content="corto", tool_calls=None)
    cliente = _ClienteOpenAIFalso([_respuesta_openai(mensaje, "length")])
    adaptador = AdaptadorOpenAI(cliente=cliente)

    turno_resultado = TurnoResultadoHerramienta(
        resultados=[ResultadoHerramienta(id_uso="call_1", contenido="42", es_error=False)]
    )
    respuesta = adaptador.responder(**{**_kwargs_comunes(), "mensajes": [TurnoUsuario(texto="hola"), turno_resultado]})

    assert respuesta.detenida_por == "longitud"
    mensajes_enviados = cliente.peticiones[0]["messages"]
    assert mensajes_enviados[-1] == {"role": "tool", "tool_call_id": "call_1", "content": "42"}


def test_adaptador_openai_sin_cliente_ni_paquete_instalado_da_error_claro(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def import_falso(nombre, *args, **kwargs):
        if nombre == "openai":
            raise ImportError("no module named openai")
        return original_import(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_falso)

    with pytest.raises(RuntimeError, match="openai"):
        AdaptadorOpenAI(clave="sk-x")


# --- AdaptadorOllama ---------------------------------------------------------

class _RespuestaHTTPFalsa:
    def __init__(self, cuerpo: dict):
        self._cuerpo = json.dumps(cuerpo).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self):
        return self._cuerpo


def test_adaptador_ollama_respuesta_de_texto(monkeypatch):
    peticiones = []

    def urlopen_falso(peticion, timeout=None):
        peticiones.append(peticion)
        return _RespuestaHTTPFalsa({"message": {"role": "assistant", "content": "Son 42, señor."}, "done": True})

    monkeypatch.setattr("jarvis.proveedores.ollama_adaptador.urllib.request.urlopen", urlopen_falso)

    respuesta = AdaptadorOllama(modelo="qwen3:8b").responder(**_kwargs_comunes())

    assert respuesta.detenida_por == "texto"
    assert respuesta.contenido == [BloqueTexto(texto="Son 42, señor.")]
    cuerpo_enviado = json.loads(peticiones[0].data)
    assert cuerpo_enviado["model"] == "algun-modelo"
    assert cuerpo_enviado["tools"][0]["function"]["name"] == "calcular"
    assert peticiones[0].full_url == "http://localhost:11434/api/chat"


def test_adaptador_ollama_tool_calls_y_argumentos_como_objeto(monkeypatch):
    def urlopen_falso(peticion, timeout=None):
        return _RespuestaHTTPFalsa({
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"function": {"name": "calcular", "arguments": {"expresion": "6*7"}}}],
            },
            "done": True,
        })

    monkeypatch.setattr("jarvis.proveedores.ollama_adaptador.urllib.request.urlopen", urlopen_falso)

    respuesta = AdaptadorOllama(modelo="qwen3:8b").responder(**_kwargs_comunes())

    assert respuesta.detenida_por == "herramienta"
    assert respuesta.contenido == [BloqueUsoHerramienta(id="ollama-0", nombre="calcular", entrada={"expresion": "6*7"})]


def test_adaptador_ollama_sin_servidor_corriendo_lanza_oserror(monkeypatch):
    import urllib.error

    def urlopen_falso(peticion, timeout=None):
        raise urllib.error.URLError("conexión rechazada")

    monkeypatch.setattr("jarvis.proveedores.ollama_adaptador.urllib.request.urlopen", urlopen_falso)

    with pytest.raises(OSError):
        AdaptadorOllama(modelo="qwen3:8b").responder(**_kwargs_comunes())


def test_listar_modelos_ollama(monkeypatch):
    def urlopen_falso(peticion, timeout=None):
        assert peticion.full_url == "http://localhost:11434/api/tags"
        return _RespuestaHTTPFalsa({"models": [{"name": "qwen3:8b"}, {"name": "qwen3-vl:4b"}]})

    monkeypatch.setattr("jarvis.proveedores.ollama_adaptador.urllib.request.urlopen", urlopen_falso)

    assert listar_modelos_ollama() == ["qwen3:8b", "qwen3-vl:4b"]


def test_listar_modelos_ollama_sin_servidor_corriendo(monkeypatch):
    import urllib.error

    def urlopen_falso(peticion, timeout=None):
        raise urllib.error.URLError("conexión rechazada")

    monkeypatch.setattr("jarvis.proveedores.ollama_adaptador.urllib.request.urlopen", urlopen_falso)

    with pytest.raises(OSError):
        listar_modelos_ollama()
