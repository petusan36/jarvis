"""Adaptador que conecta el puerto ``ProveedorIA`` con la API de Anthropic.

Reproduce exactamente la llamada que hacía antes ``Cerebro`` de forma
directa (mismas betas, mismo ``output_config`` de esfuerzo), para no cambiar
el comportamiento existente.
"""

from __future__ import annotations

from typing import Any

import anthropic

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

# Mapeo de anthropic ``stop_reason`` al vocabulario neutral del puerto.
_DETENIDA_POR = {
    "refusal": "rechazo",
    "tool_use": "herramienta",
    "max_tokens": "longitud",
}


class AdaptadorAnthropic(ProveedorIA):
    """Envuelve ``anthropic.Anthropic`` (modo API, con las betas de Jarvis)."""

    def __init__(self, cliente: Any | None = None):
        self._cliente = cliente or anthropic.Anthropic()

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
        respuesta = self._cliente.beta.messages.create(
            model=modelo,
            max_tokens=max_tokens,
            system=sistema,
            tools=herramientas,
            messages=[_a_mensaje_nativo(t) for t in mensajes],
            output_config={"effort": esfuerzo},
            # Si el modelo rechaza la petición, la API reintenta con otro modelo.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        contenido = _normalizar_contenido(respuesta.content)
        detenida_por = _DETENIDA_POR.get(respuesta.stop_reason, "texto")
        # Se guarda el contenido completo (incluidos bloques de razonamiento)
        # para que la conversación siga siendo válida en la siguiente vuelta.
        return RespuestaIA(contenido=contenido, detenida_por=detenida_por, bruto=respuesta.content)


def _normalizar_contenido(bloques: list[Any]) -> list[BloqueContenido]:
    contenido: list[BloqueContenido] = []
    for bloque in bloques:
        if bloque.type == "text":
            contenido.append(BloqueTexto(texto=bloque.text))
        elif bloque.type == "tool_use":
            contenido.append(BloqueUsoHerramienta(id=bloque.id, nombre=bloque.name, entrada=bloque.input))
        # otros tipos (p. ej. razonamiento) no le interesan a Cerebro: viajan
        # igual en ``bruto`` para la próxima vuelta.
    return contenido


def _a_mensaje_nativo(turno: Turno) -> dict[str, Any]:
    if isinstance(turno, TurnoUsuario):
        return {"role": "user", "content": turno.texto}
    if isinstance(turno, TurnoAsistente):
        contenido = turno.bruto if turno.bruto is not None else _reconstruir_asistente(turno.contenido)
        return {"role": "assistant", "content": contenido}
    if isinstance(turno, TurnoResultadoHerramienta):
        return {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": r.id_uso, "content": r.contenido, "is_error": r.es_error}
                for r in turno.resultados
            ],
        }
    raise TypeError(f"Turno no soportado: {type(turno)!r}")


def _reconstruir_asistente(contenido: list[BloqueContenido]) -> list[dict[str, Any]]:
    """Reconstruye bloques nativos cuando no hay ``bruto`` (p. ej. en tests)."""
    bloques: list[dict[str, Any]] = []
    for b in contenido:
        if isinstance(b, BloqueTexto):
            bloques.append({"type": "text", "text": b.texto})
        else:
            bloques.append({"type": "tool_use", "id": b.id, "name": b.nombre, "input": b.entrada})
    return bloques
