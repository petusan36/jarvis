"""Puerto y adaptadores de proveedores de IA.

``Cerebro`` depende solo de ``ProveedorIA`` (puerto). Los adaptadores
(``AdaptadorAnthropic``, ``AdaptadorOllama``, ``AdaptadorCodexResponses``)
viven acá y son intercambiables sin que ``Cerebro`` se entere de qué
proveedor hay detrás.

Nota: Claude por suscripción sigue usando ``cerebro_suscripcion.py``
(Claude Agent SDK) en vez de este puerto — es un mecanismo bien distinto
(SDK con servidor MCP embebido), no un simple cliente HTTP.
"""

from __future__ import annotations

from .anthropic_adaptador import AdaptadorAnthropic
from .codex_responses_adaptador import AdaptadorCodexResponses, MODELO_POR_DEFECTO as MODELO_CODEX_POR_DEFECTO
from .ollama_adaptador import AdaptadorOllama, listar_modelos_ollama
from .puerto import (
    BloqueContenido,
    BloqueTexto,
    BloqueUsoHerramienta,
    ProveedorIA,
    RespuestaIA,
    ResultadoHerramienta,
    Turno,
    TurnoAsistente,
    TurnoResultadoHerramienta,
    TurnoUsuario,
)

__all__ = [
    "AdaptadorAnthropic",
    "AdaptadorCodexResponses",
    "AdaptadorOllama",
    "BloqueContenido",
    "BloqueTexto",
    "BloqueUsoHerramienta",
    "MODELO_CODEX_POR_DEFECTO",
    "ProveedorIA",
    "RespuestaIA",
    "ResultadoHerramienta",
    "Turno",
    "TurnoAsistente",
    "TurnoResultadoHerramienta",
    "TurnoUsuario",
    "listar_modelos_ollama",
]
