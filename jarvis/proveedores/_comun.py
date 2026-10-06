"""Helpers compartidos entre adaptadores que hablan el formato de
function-calling de estilo OpenAI (OpenAI y Ollama/Qwen3 lo comparten)."""

from __future__ import annotations

from typing import Any


def herramienta_a_function_calling(h: dict[str, Any]) -> dict[str, Any]:
    """Traduce una definición de herramienta del formato Anthropic tool-use
    (``name``, ``description``, ``input_schema``) al formato de function
    calling que usan tanto OpenAI como Ollama: ``{"type": "function",
    "function": {...}}`` con el esquema JSON en ``parameters``."""
    return {
        "type": "function",
        "function": {
            "name": h["name"],
            "description": h["description"],
            "parameters": h["input_schema"],
            "strict": h.get("strict", False),
        },
    }
