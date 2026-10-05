"""Puerto y adaptadores de proveedores de IA.

``Cerebro`` depende solo de ``ProveedorIA`` (puerto). Los adaptadores
(``AdaptadorAnthropic``, ``AdaptadorOpenAI``, ``AdaptadorOllama``) viven acá
y son intercambiables sin que ``Cerebro`` se entere de qué proveedor hay
detrás.
"""

from __future__ import annotations

from .anthropic_adaptador import AdaptadorAnthropic
from .ollama_adaptador import AdaptadorOllama, listar_modelos_ollama
from .openai_adaptador import AdaptadorOpenAI
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
    "AdaptadorOllama",
    "AdaptadorOpenAI",
    "BloqueContenido",
    "BloqueTexto",
    "BloqueUsoHerramienta",
    "ProveedorIA",
    "RespuestaIA",
    "ResultadoHerramienta",
    "Turno",
    "TurnoAsistente",
    "TurnoResultadoHerramienta",
    "TurnoUsuario",
    "listar_modelos_ollama",
]
