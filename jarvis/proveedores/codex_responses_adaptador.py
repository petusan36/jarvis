"""Adaptador que habla con el endpoint interno que usa Codex CLI cuando
estás logueado con tu cuenta de ChatGPT (``codex login``), en vez de con
una clave de API.

Todo lo de abajo está verificado de verdad contra la API real (no es
documentación pública: es un endpoint interno de ChatGPT, no
``api.openai.com``):

- Endpoint: ``POST https://chatgpt.com/backend-api/codex/responses``.
- El token de la sesión de Codex CLI (``~/.codex/auth.json`` o
  ``$CODEX_HOME/auth.json``, campo ``tokens.access_token``) sirve para
  este endpoint, pero NO para la API pública: su scope
  (``api.connectors.read``/``api.connectors.invoke``, sin
  ``api.responses.write``) hace que ``api.openai.com/v1/responses``
  responda 401 "Missing scopes". No lo intentes ahí.
- El body tiene que llevar ``"store": false`` y ``"stream": true``
  siempre — con cualquier otro valor la API responde 400. Al ser
  ``stream: true``, la respuesta es Server-Sent Events (texto plano
  ``event:``/``data:``), nunca JSON de una sola pieza: hay que parsear
  SSE a mano, no hay cliente oficial para este endpoint.
- ``"model"`` tiene que ser el modelo real que usa tu cuenta de ChatGPT a
  través de Codex (confirmado corriendo ``codex exec ... 2>&1 | grep
  model:``); un nombre público como ``gpt-5`` da 400 "not supported when
  using Codex with a ChatGPT account". Puede cambiar sin aviso si OpenAI
  renombra el modelo en el backend — por eso es una constante con
  comentario, no algo mágico.
- El formato de tools es el de la Responses API: plano (``{"type":
  "function", "name", "description", "parameters"}``), DISTINTO al
  formato anidado ``{"function": {...}}`` de Chat Completions que usa
  ``AdaptadorOllama`` — ver ``_comun.py::herramienta_a_responses_api``.
- Como ``store`` es siempre ``false``, no hay memoria del lado del
  servidor (``previous_response_id`` no sirve acá): cada llamada manda la
  conversación completa en ``input``, igual que los demás adaptadores de
  este puerto. Confirmado con una prueba real de 3 turnos (texto) y de
  tool-calling con ida y vuelta completa (function_call ->
  function_call_output -> respuesta final usando el resultado).
- No hace falta preservar ningún "bruto" entre vueltas (a diferencia de
  Anthropic): reconstruir el turno del asistente a partir de los bloques
  normalizados (texto + function_call) alcanza para que la conversación
  siga siendo coherente — verificado con la prueba de 3 turnos.

TODO sin verificar: el refresh del token cuando vence
(``tokens.refresh_token``, probablemente contra
``https://auth.openai.com/oauth/token`` con ``grant_type=refresh_token``,
pero no se confirmó contra la API real). Mientras tanto, si el token está
vencido o la API devuelve 401, el error le pide al usuario que corra
``codex login`` de nuevo — no se intenta refrescar solo.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ._comun import herramienta_a_responses_api
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

URL_RESPONSES = "https://chatgpt.com/backend-api/codex/responses"

# Modelo real que usa Codex CLI con cuenta de ChatGPT al momento de escribir
# esto (confirmado con `codex exec ... 2>&1 | grep model:`). Puede cambiar
# sin aviso del lado de OpenAI.
MODELO_POR_DEFECTO = "gpt-6.1-sol"

TIMEOUT_SEGUNDOS = 120

AbrirConexion = Callable[..., Any]


def _ruta_auth() -> Path:
    base = os.environ.get("CODEX_HOME")
    if base:
        return Path(base).expanduser() / "auth.json"
    return Path.home() / ".codex" / "auth.json"


def leer_token_codex() -> str:
    """Lee el ``access_token`` de la sesión de Codex CLI ya logueada.

    No pide ni guarda ninguna clave propia: solo lee lo que ``codex
    login`` ya dejó en disco. Si no existe o está vencido, pide volver a
    hacer login en vez de inventar algo."""
    ruta = _ruta_auth()
    if not ruta.is_file():
        raise RuntimeError(
            "No encuentro la sesión de Codex. Ejecuta `codex login` e inicia sesión con tu cuenta."
        )
    try:
        datos = json.loads(ruta.read_text("utf-8"))
        token = datos["tokens"]["access_token"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise RuntimeError(f"No puedo leer la sesión de Codex ({ruta}): {error}") from error

    vencimiento = _exp_del_jwt(token)
    if vencimiento is not None and vencimiento < time.time():
        raise RuntimeError(
            "Tu sesión de Codex venció. Ejecuta `codex login` de nuevo.\n"
            "(todavía no sabemos refrescarla solos: ver TODO en codex_responses_adaptador.py)"
        )
    return token


def _exp_del_jwt(token: str) -> float | None:
    """Decodifica (sin verificar firma — no hace falta, solo lo usamos
    para decidir si pedir `codex login` de nuevo) el payload de un JWT
    para leer su campo ``exp``."""
    partes = token.split(".")
    if len(partes) != 3:
        return None
    relleno = "=" * (-len(partes[1]) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(partes[1] + relleno))
    except (ValueError, json.JSONDecodeError):
        return None
    return payload.get("exp")


class AdaptadorCodexResponses(ProveedorIA):
    """Habla con el endpoint interno de Codex/ChatGPT (Responses API)."""

    def __init__(self, token: str | None = None, abrir: AbrirConexion = urllib.request.urlopen):
        self._token = token or leer_token_codex()
        self._abrir = abrir

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
        cuerpo = {
            "model": modelo or MODELO_POR_DEFECTO,
            "instructions": sistema,
            "input": [item for turno in mensajes for item in _turno_a_items(turno)],
            "store": False,
            "stream": True,
            "max_output_tokens": max_tokens,
            "reasoning": {"effort": esfuerzo},
            "tools": [herramienta_a_responses_api(h) for h in herramientas],
        }
        datos = json.dumps(cuerpo).encode("utf-8")
        peticion = urllib.request.Request(
            URL_RESPONSES,
            data=datos,
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._token}"},
        )
        try:
            with self._abrir(peticion, timeout=TIMEOUT_SEGUNDOS) as respuesta:
                lineas = (linea.decode("utf-8") if isinstance(linea, bytes) else linea for linea in respuesta)
                return _parsear_sse(lineas)
        except urllib.error.HTTPError as error:
            cuerpo_error = error.read().decode("utf-8", errors="replace")
            if error.code == 401:
                raise OSError("Tu sesión de Codex venció o no es válida. Ejecuta `codex login` de nuevo.") from error
            raise OSError(f"Codex devolvió un error ({error.code}): {_resumir_error(cuerpo_error)}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise OSError(f"no se pudo conectar con Codex ({error})") from error


def _resumir_error(cuerpo: str) -> str:
    try:
        datos = json.loads(cuerpo)
    except json.JSONDecodeError:
        return cuerpo[:300]
    error = datos.get("error")
    if isinstance(error, dict) and error.get("message"):
        return error["message"]
    return cuerpo[:300]


def _turno_a_items(turno: Turno) -> list[dict[str, Any]]:
    if isinstance(turno, TurnoUsuario):
        return [{"role": "user", "content": turno.texto}]
    if isinstance(turno, TurnoAsistente):
        items: list[dict[str, Any]] = []
        texto = "".join(b.texto for b in turno.contenido if isinstance(b, BloqueTexto))
        if texto:
            items.append({"role": "assistant", "content": texto})
        for bloque in turno.contenido:
            if isinstance(bloque, BloqueUsoHerramienta):
                items.append({
                    "type": "function_call",
                    "call_id": bloque.id,
                    "name": bloque.nombre,
                    "arguments": json.dumps(bloque.entrada),
                })
        return items
    if isinstance(turno, TurnoResultadoHerramienta):
        return [
            {"type": "function_call_output", "call_id": r.id_uso, "output": r.contenido}
            for r in turno.resultados
        ]
    raise TypeError(f"Turno no soportado: {type(turno)!r}")


def _parsear_sse(lineas) -> RespuestaIA:
    """Parsea el stream de eventos SSE de la Responses API.

    Eventos usados (confirmados contra la API real):
    - ``response.output_item.added`` con ``item.type == "function_call"``:
      registra ``call_id``/``name`` por ``item_id``, para emparejar con...
    - ``response.function_call_arguments.done``: los argumentos completos
      (string JSON) de esa llamada, emparejados por ``item_id``.
    - ``response.output_text.delta`` / ``.done``: texto de la respuesta;
      se usa ``.done`` si llega (ya viene completo), si no se acumulan
      los ``delta``.
    - ``response.completed``: si el ``status`` final es ``incomplete``,
      se marca como respuesta cortada por longitud.
    - ``response.failed`` / ``error``: se traduce a un ``OSError`` claro.
    """
    texto_final: str | None = None
    texto_acumulado: list[str] = []
    llamadas_por_item: dict[str, dict[str, str]] = {}
    bloques_herramienta: list[BloqueUsoHerramienta] = []
    incompleta = False

    for linea in lineas:
        linea = linea.strip()
        if not linea or not linea.startswith("data:"):
            continue
        cuerpo = linea[len("data:"):].strip()
        try:
            evento = json.loads(cuerpo)
        except json.JSONDecodeError:
            continue
        tipo = evento.get("type")

        if tipo == "response.output_item.added":
            item = evento.get("item") or {}
            if item.get("type") == "function_call":
                llamadas_por_item[item.get("id")] = {
                    "call_id": item.get("call_id"),
                    "name": item.get("name"),
                }
        elif tipo == "response.function_call_arguments.done":
            info = llamadas_por_item.get(evento.get("item_id"))
            if info:
                try:
                    entrada = json.loads(evento.get("arguments") or "{}")
                except json.JSONDecodeError:
                    entrada = {}
                bloques_herramienta.append(
                    BloqueUsoHerramienta(id=info["call_id"], nombre=info["name"], entrada=entrada)
                )
        elif tipo == "response.output_text.delta":
            texto_acumulado.append(evento.get("delta") or "")
        elif tipo == "response.output_text.done":
            texto_final = evento.get("text")
        elif tipo == "response.completed":
            estado = (evento.get("response") or {}).get("status")
            incompleta = estado == "incomplete"
        elif tipo in ("response.failed", "error"):
            datos_error = evento.get("response", {}).get("error") if "response" in evento else evento.get("error")
            mensaje = datos_error.get("message") if isinstance(datos_error, dict) else str(datos_error or evento)
            raise OSError(f"Codex devolvió un error: {mensaje}")

    contenido: list[BloqueContenido] = []
    texto = texto_final if texto_final is not None else "".join(texto_acumulado)
    if texto:
        contenido.append(BloqueTexto(texto=texto))
    contenido.extend(bloques_herramienta)

    if bloques_herramienta:
        detenida_por = "herramienta"
    elif incompleta:
        detenida_por = "longitud"
    else:
        detenida_por = "texto"

    return RespuestaIA(contenido=contenido, detenida_por=detenida_por, bruto=None)
