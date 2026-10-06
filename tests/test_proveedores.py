"""Pruebas de los adaptadores de IA (puerto ProveedorIA): todas sin red real,
mockeando el SDK/HTTP de cada proveedor."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from jarvis.proveedores import (
    AdaptadorAnthropic,
    AdaptadorCodexResponses,
    AdaptadorOllama,
    BloqueTexto,
    BloqueUsoHerramienta,
    ResultadoHerramienta,
    TurnoAsistente,
    TurnoResultadoHerramienta,
    TurnoUsuario,
    listar_modelos_ollama,
)
from jarvis.proveedores._comun import herramienta_a_function_calling, herramienta_a_responses_api

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


# --- AdaptadorCodexResponses -------------------------------------------------

def test_herramienta_a_responses_api_traduce_el_esquema_plano():
    traducida = herramienta_a_responses_api(HERRAMIENTAS[0])
    assert traducida == {
        "type": "function",
        "name": "calcular",
        "description": "Evalúa una expresión matemática.",
        "parameters": HERRAMIENTAS[0]["input_schema"],
        "strict": True,
    }
    assert "function" not in traducida  # a diferencia del formato de Chat Completions/Ollama


class _RespuestaSSEFalsa:
    """Imita lo que devuelve urlopen cuando se itera línea por línea un
    stream de Server-Sent Events."""

    def __init__(self, lineas: list[bytes]):
        self._lineas = lineas

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def __iter__(self):
        return iter(self._lineas)


def _sse(eventos: list[dict]) -> list[bytes]:
    lineas = []
    for evento in eventos:
        lineas.append(f"data: {json.dumps(evento)}\n".encode())
        lineas.append(b"\n")
    return lineas


def test_adaptador_codex_responder_texto(monkeypatch):
    peticiones = []

    def abrir_falso(peticion, timeout=None):
        peticiones.append(peticion)
        return _RespuestaSSEFalsa(_sse([
            {"type": "response.output_text.delta", "delta": "Son "},
            {"type": "response.output_text.delta", "delta": "42."},
            {"type": "response.output_text.done", "text": "Son 42, señor."},
            {"type": "response.completed", "response": {"status": "completed"}},
        ]))

    adaptador = AdaptadorCodexResponses(token="tok-123", abrir=abrir_falso)
    respuesta = adaptador.responder(**_kwargs_comunes())

    assert respuesta.detenida_por == "texto"
    assert respuesta.contenido == [BloqueTexto(texto="Son 42, señor.")]

    peticion = peticiones[0]
    assert peticion.full_url == "https://chatgpt.com/backend-api/codex/responses"
    assert peticion.get_header("Authorization") == "Bearer tok-123"
    cuerpo = json.loads(peticion.data)
    assert cuerpo["model"] == "algun-modelo"
    assert cuerpo["instructions"] == "Sos Jarvis."
    assert cuerpo["store"] is False and cuerpo["stream"] is True
    assert cuerpo["input"] == [{"role": "user", "content": "¿Cuánto es 6 por 7?"}]
    assert cuerpo["tools"][0] == {
        "type": "function", "name": "calcular",
        "description": "Evalúa una expresión matemática.",
        "parameters": HERRAMIENTAS[0]["input_schema"], "strict": True,
    }


def test_adaptador_codex_responder_con_herramienta():
    def abrir_falso(peticion, timeout=None):
        return _RespuestaSSEFalsa(_sse([
            {"type": "response.output_item.added",
             "item": {"id": "item_1", "type": "function_call", "call_id": "call_abc", "name": "calcular"}},
            {"type": "response.function_call_arguments.done",
             "item_id": "item_1", "arguments": json.dumps({"expresion": "6*7"})},
            {"type": "response.completed", "response": {"status": "completed"}},
        ]))

    adaptador = AdaptadorCodexResponses(token="tok-123", abrir=abrir_falso)
    respuesta = adaptador.responder(**_kwargs_comunes())

    assert respuesta.detenida_por == "herramienta"
    assert respuesta.contenido == [BloqueUsoHerramienta(id="call_abc", nombre="calcular", entrada={"expresion": "6*7"})]


def test_adaptador_codex_respuesta_incompleta_es_longitud():
    def abrir_falso(peticion, timeout=None):
        return _RespuestaSSEFalsa(_sse([
            {"type": "response.output_text.done", "text": "cortad"},
            {"type": "response.completed", "response": {"status": "incomplete"}},
        ]))

    adaptador = AdaptadorCodexResponses(token="tok-123", abrir=abrir_falso)
    respuesta = adaptador.responder(**_kwargs_comunes())

    assert respuesta.detenida_por == "longitud"


def test_adaptador_codex_reconstruye_turnos_sin_bruto():
    """Sin 'store' server-side, cada llamada manda la conversación
    completa: un turno de usuario, uno de asistente que llamó una
    herramienta, y el resultado de esa herramienta."""
    peticiones = []

    def abrir_falso(peticion, timeout=None):
        peticiones.append(peticion)
        return _RespuestaSSEFalsa(_sse([
            {"type": "response.output_text.done", "text": "listo"},
            {"type": "response.completed", "response": {"status": "completed"}},
        ]))

    mensajes = [
        TurnoUsuario(texto="¿Cuánto es 6 por 7?"),
        TurnoAsistente(contenido=[BloqueUsoHerramienta(id="call_abc", nombre="calcular", entrada={"expresion": "6*7"})]),
        TurnoResultadoHerramienta(resultados=[ResultadoHerramienta(id_uso="call_abc", contenido="42", es_error=False)]),
    ]
    adaptador = AdaptadorCodexResponses(token="tok-123", abrir=abrir_falso)
    adaptador.responder(**{**_kwargs_comunes(), "mensajes": mensajes})

    cuerpo = json.loads(peticiones[0].data)
    assert cuerpo["input"] == [
        {"role": "user", "content": "¿Cuánto es 6 por 7?"},
        {"type": "function_call", "call_id": "call_abc", "name": "calcular", "arguments": '{"expresion": "6*7"}'},
        {"type": "function_call_output", "call_id": "call_abc", "output": "42"},
    ]


def test_adaptador_codex_error_401_pide_relogin():
    import urllib.error

    def abrir_falso(peticion, timeout=None):
        raise urllib.error.HTTPError(peticion.full_url, 401, "Unauthorized", {}, __import__("io").BytesIO(b"{}"))

    adaptador = AdaptadorCodexResponses(token="tok-vencido", abrir=abrir_falso)
    with pytest.raises(OSError, match="codex login"):
        adaptador.responder(**_kwargs_comunes())


def test_adaptador_codex_error_400_incluye_el_mensaje_de_la_api():
    import io
    import urllib.error

    def abrir_falso(peticion, timeout=None):
        cuerpo = json.dumps({"error": {"message": "Store must be set to false"}}).encode()
        raise urllib.error.HTTPError(peticion.full_url, 400, "Bad Request", {}, io.BytesIO(cuerpo))

    adaptador = AdaptadorCodexResponses(token="tok-123", abrir=abrir_falso)
    with pytest.raises(OSError, match="Store must be set to false"):
        adaptador.responder(**_kwargs_comunes())


def test_adaptador_codex_sin_conexion_lanza_oserror():
    import urllib.error

    def abrir_falso(peticion, timeout=None):
        raise urllib.error.URLError("conexión rechazada")

    adaptador = AdaptadorCodexResponses(token="tok-123", abrir=abrir_falso)
    with pytest.raises(OSError):
        adaptador.responder(**_kwargs_comunes())


def test_adaptador_codex_evento_de_error_en_el_stream():
    def abrir_falso(peticion, timeout=None):
        return _RespuestaSSEFalsa(_sse([
            {"type": "response.failed", "response": {"error": {"message": "algo se rompió"}}},
        ]))

    adaptador = AdaptadorCodexResponses(token="tok-123", abrir=abrir_falso)
    with pytest.raises(OSError, match="algo se rompió"):
        adaptador.responder(**_kwargs_comunes())


def test_adaptador_codex_usa_leer_token_si_no_se_inyecta(monkeypatch):
    monkeypatch.setattr("jarvis.proveedores.codex_responses_adaptador.leer_token_codex", lambda: "tok-del-disco")

    def abrir_falso(peticion, timeout=None):
        assert peticion.get_header("Authorization") == "Bearer tok-del-disco"
        return _RespuestaSSEFalsa(_sse([{"type": "response.completed", "response": {"status": "completed"}}]))

    AdaptadorCodexResponses(abrir=abrir_falso).responder(**_kwargs_comunes())
