"""Puerto y adaptadores de proveedores de IA.

``Cerebro`` depende solo de ``ProveedorIA`` (puerto). Los adaptadores
(``AdaptadorAnthropic``, ``AdaptadorOllama``) viven acá y son
intercambiables sin que ``Cerebro`` se entere de qué proveedor hay detrás.

Nota: no hay adaptador de OpenAI. Codex/OpenAI se conecta vía
``jarvis.cerebro_codex.CerebroCodex`` (sesión de Codex CLI, sin clave de
API) en lugar de este puerto, igual que Claude por suscripción usa
``cerebro_suscripcion.py``.
"""

from __future__ import annotations

from .anthropic_adaptador import AdaptadorAnthropic
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
    "AdaptadorOllama",
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
