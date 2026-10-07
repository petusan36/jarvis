"""Adaptador que habla con la API local de Ollama (``/api/chat``) y traduce
el formato de herramientas al que espera Ollama/Qwen3 (el mismo estilo
function-calling que OpenAI, pero con los argumentos de cada llamada como
objeto JSON en vez de como string).

Usa ``urllib.request`` (como ya hace ``musica.py`` para la API de YouTube)
en vez de añadir una dependencia nueva solo para esto.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
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

URL_POR_DEFECTO = "http://localhost:11434"
_TIMEOUT_SEGUNDOS = 120  # los modelos locales pueden tardar más que una API en la nube


class AdaptadorOllama(ProveedorIA):
    """Habla con un servidor Ollama local vía HTTP."""

    def __init__(self, modelo: str, url: str = URL_POR_DEFECTO):
        self.modelo = modelo
        self.url = url.rstrip("/")

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

        cuerpo = {
            "model": modelo or self.modelo,
            "messages": nativos,
            "tools": [herramienta_a_function_calling(h) for h in herramientas],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        datos = _peticion_json(f"{self.url}/api/chat", cuerpo)

        mensaje = datos.get("message", {})
        contenido = _normalizar_contenido(mensaje)
        if mensaje.get("tool_calls"):
            detenida_por = "herramienta"
        elif datos.get("done_reason") == "length":
            detenida_por = "longitud"
        else:
            detenida_por = "texto"
        bruto = {
            "role": "assistant",
            "content": mensaje.get("content"),
            "tool_calls": mensaje.get("tool_calls") or None,
        }
        return RespuestaIA(contenido=contenido, detenida_por=detenida_por, bruto=bruto)


def listar_modelos_ollama(url: str = URL_POR_DEFECTO) -> list[str]:
    """Consulta ``GET /api/tags`` y devuelve los nombres de los modelos
    instalados localmente (p. ej. ``["qwen3:8b", "qwen3-vl:4b"]``).

    Lanza ``OSError`` si Ollama no está corriendo o no responde a tiempo;
    quien llame decide cómo mostrar ese error (no se traga nada aquí)."""
    peticion = urllib.request.Request(f"{url.rstrip('/')}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(peticion, timeout=5) as respuesta:
            datos = json.loads(respuesta.read())
    except (urllib.error.URLError, TimeoutError) as error:
        raise OSError(f"no se pudo conectar con Ollama en {url}") from error
    except json.JSONDecodeError as error:
        raise OSError("Ollama respondió algo que no es JSON válido") from error
    return [m["name"] for m in datos.get("models", [])]


def _peticion_json(url: str, cuerpo: dict[str, Any]) -> dict[str, Any]:
    datos = json.dumps(cuerpo).encode("utf-8")
    peticion = urllib.request.Request(
        url, data=datos, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(peticion, timeout=_TIMEOUT_SEGUNDOS) as respuesta:
            return json.loads(respuesta.read())
    except (urllib.error.URLError, TimeoutError) as error:
        raise OSError(f"no se pudo conectar con Ollama en {url}") from error
    except json.JSONDecodeError as error:
        raise OSError("Ollama respondió algo que no es JSON válido") from error


def _normalizar_contenido(mensaje: dict[str, Any]) -> list[BloqueContenido]:
    contenido: list[BloqueContenido] = []
    if mensaje.get("content"):
        contenido.append(BloqueTexto(texto=mensaje["content"]))
    for i, llamada in enumerate(mensaje.get("tool_calls") or []):
        funcion = llamada.get("function", {})
        contenido.append(
            BloqueUsoHerramienta(
                id=llamada.get("id") or f"ollama-{i}",
                nombre=funcion.get("name", ""),
                entrada=funcion.get("arguments") or {},
            )
        )
    return contenido


def _turno_a_mensajes(turno: Turno) -> list[dict[str, Any]]:
    if isinstance(turno, TurnoUsuario):
        return [{"role": "user", "content": turno.texto}]
    if isinstance(turno, TurnoAsistente):
        return [turno.bruto if turno.bruto is not None else _reconstruir_asistente(turno.contenido)]
    if isinstance(turno, TurnoResultadoHerramienta):
        # Ollama no exige emparejar por id: un mensaje "tool" por resultado, en orden.
        return [{"role": "tool", "content": r.contenido} for r in turno.resultados]
    raise TypeError(f"Turno no soportado: {type(turno)!r}")


def _reconstruir_asistente(contenido: list[BloqueContenido]) -> dict[str, Any]:
    """Reconstruye el mensaje nativo cuando no hay ``bruto`` (p. ej. en tests)."""
    texto = "".join(b.texto for b in contenido if isinstance(b, BloqueTexto)) or None
    llamadas = [
        {"function": {"name": b.nombre, "arguments": b.entrada}}
        for b in contenido
        if isinstance(b, BloqueUsoHerramienta)
    ]
    return {"role": "assistant", "content": texto, "tool_calls": llamadas or None}
