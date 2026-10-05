"""Adaptador que traduce el puerto ``ProveedorIA`` al formato de
function-calling de OpenAI (Chat Completions).

El SDK de ``openai`` es una dependencia opcional: solo se importa si de
verdad se usa este adaptador (sin cliente inyectado), igual que Jarvis ya
hace con ``claude_agent_sdk`` para el modo suscripción.
"""

from __future__ import annotations

import json
from typing import Any

from ._comun import herramienta_a_function_calling
from .puerto import (
    BloqueContenido,
    BloqueTexto,
    BloqueUsoHerramienta,
    ProveedorIA,
    RespuestaIA,
    Turno,
    TurnoAsistente,
    TurnoResultadoHerramienta,
    TurnoUsuario,
)

# Mapeo de ``finish_reason`` de OpenAI al vocabulario neutral del puerto.
_DETENIDA_POR = {
    "tool_calls": "herramienta",
    "length": "longitud",
    "content_filter": "rechazo",
}


class AdaptadorOpenAI(ProveedorIA):
    """Envuelve ``openai.OpenAI`` (Chat Completions + tools)."""

    def __init__(self, clave: str | None = None, cliente: Any | None = None):
        if cliente is not None:
            self._cliente = cliente
        else:
            try:
                import openai
            except ImportError as error:
                raise RuntimeError(
                    "Falta el paquete openai. Instálalo con: pip install openai"
                ) from error
            self._cliente = openai.OpenAI(api_key=clave)

    def responder(
        self,
        *,
        mensajes: list[Turno],
        sistema: str,
        herramientas: list[dict[str, Any]],
        modelo: str,
        max_tokens: int,
        esfuerzo: str,
    ) -> RespuestaIA:
        nativos: list[dict[str, Any]] = [{"role": "system", "content": sistema}]
        for turno in mensajes:
            nativos.extend(_turno_a_mensajes(turno))

        respuesta = self._cliente.chat.completions.create(
            model=modelo,
            max_completion_tokens=max_tokens,
            messages=nativos,
            tools=[herramienta_a_function_calling(h) for h in herramientas],
        )
        eleccion = respuesta.choices[0]
        contenido = _normalizar_contenido(eleccion.message)
        detenida_por = _DETENIDA_POR.get(eleccion.finish_reason, "texto")
        return RespuestaIA(contenido=contenido, detenida_por=detenida_por, bruto=_mensaje_a_bruto(eleccion.message))


def _normalizar_contenido(mensaje: Any) -> list[BloqueContenido]:
    contenido: list[BloqueContenido] = []
    if mensaje.content:
        contenido.append(BloqueTexto(texto=mensaje.content))
    for llamada in mensaje.tool_calls or []:
        contenido.append(
            BloqueUsoHerramienta(
                id=llamada.id,
                nombre=llamada.function.name,
                entrada=json.loads(llamada.function.arguments or "{}"),
            )
        )
    return contenido


def _mensaje_a_bruto(mensaje: Any) -> dict[str, Any]:
    """Convierte la respuesta del SDK en un dict plano, listo para
    reenviarlo tal cual en la próxima vuelta (el objeto del SDK no siempre
    es serializable como mensaje de entrada)."""
    llamadas = [
        {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
        for tc in (mensaje.tool_calls or [])
    ]
    return {"role": "assistant", "content": mensaje.content, "tool_calls": llamadas or None}


def _turno_a_mensajes(turno: Turno) -> list[dict[str, Any]]:
    if isinstance(turno, TurnoUsuario):
        return [{"role": "user", "content": turno.texto}]
    if isinstance(turno, TurnoAsistente):
        return [turno.bruto if turno.bruto is not None else _reconstruir_asistente(turno.contenido)]
    if isinstance(turno, TurnoResultadoHerramienta):
        return [{"role": "tool", "tool_call_id": r.id_uso, "content": r.contenido} for r in turno.resultados]
    raise TypeError(f"Turno no soportado: {type(turno)!r}")


def _reconstruir_asistente(contenido: list[BloqueContenido]) -> dict[str, Any]:
    """Reconstruye el mensaje nativo cuando no hay ``bruto`` (p. ej. en tests)."""
    texto = "".join(b.texto for b in contenido if isinstance(b, BloqueTexto)) or None
    llamadas = [
        {"id": b.id, "type": "function", "function": {"name": b.nombre, "arguments": json.dumps(b.entrada)}}
        for b in contenido
        if isinstance(b, BloqueUsoHerramienta)
    ]
    return {"role": "assistant", "content": texto, "tool_calls": llamadas or None}
