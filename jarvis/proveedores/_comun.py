"""Helpers compartidos entre adaptadores: traducen las definiciones de
herramientas de Jarvis (formato Anthropic tool-use: ``name``,
``description``, ``input_schema``) a los distintos formatos de
function-calling que habla cada proveedor."""

from __future__ import annotations

from typing import Any


def herramienta_a_function_calling(h: dict[str, Any]) -> dict[str, Any]:
    """Formato de function-calling estilo Chat Completions, que usa
    Ollama/Qwen3: ``{"type": "function", "function": {...}}`` con el
    esquema JSON anidado en ``parameters``."""
    return {
        "type": "function",
        "function": {
            "name": h["name"],
            "description": h["description"],
            "parameters": h["input_schema"],
            "strict": h.get("strict", False),
        },
    }


def herramienta_a_responses_api(h: dict[str, Any]) -> dict[str, Any]:
    """Formato de function-calling de la Responses API (la que usa el
    endpoint interno de Codex/ChatGPT) — plano, SIN el nivel anidado
    ``function`` que usa Chat Completions. Verificado contra la API real:
    la respuesta eco de ``tools`` confirma este esquema exacto."""
    return {
        "type": "function",
        "name": h["name"],
        "description": h["description"],
        "parameters": h["input_schema"],
        "strict": h.get("strict", False),
    }
