"""Cerebro alternativo que usa tu suscripción de Claude (Pro/Max) en lugar de una clave de API.

Funciona a través del Claude Agent SDK, que lanza Claude Code en tu equipo con la
sesión con la que ya iniciaste sesión (`claude` → `/login`). Las herramientas de
Jarvis se le pasan como un servidor MCP local, y las herramientas propias de
Claude Code (terminal, editar archivos...) quedan desactivadas.

Pensado solo para uso personal en tu propio equipo: no lo compartas con otras
personas usando tu cuenta.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import aclosing
from typing import Any

from .cerebro import INSTRUCCIONES, MAX_VUELTAS
from .config import Config
from .herramientas import Herramientas

SERVIDOR = "jarvis"


class CerebroSuscripcion:
    def __init__(self, config: Config, herramientas: Herramientas, cliente: Any | None = None):
        try:
            import claude_agent_sdk  # noqa: F401
        except ImportError as error:
            raise RuntimeError(
                "Falta el modo suscripción. Instálalo con: pip install -e ."
            ) from error
        self.config = config
        self.herramientas = herramientas
        self._bucle = asyncio.new_event_loop()
        self._cliente = cliente

    def responder(self, texto_usuario: str, es_dueño: bool = True) -> str:
        self.herramientas.nuevo_turno(texto_usuario, es_dueño)
        return self._bucle.run_until_complete(self._responder(texto_usuario))

    def olvidar(self) -> None:
        if self._cliente is not None:
            self._bucle.run_until_complete(self._cliente.disconnect())
            self._cliente = None

    def cerrar(self) -> None:
        self.olvidar()
        self._bucle.close()

    async def _responder(self, texto_usuario: str) -> str:
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

        if self._cliente is None:
            self._cliente = await self._conectar()

        await self._cliente.query(texto_usuario)
        partes: list[str] = []
        async with aclosing(self._cliente.receive_response()) as mensajes:
            async for mensaje in mensajes:
                if isinstance(mensaje, AssistantMessage):
                    partes += [b.text for b in mensaje.content if isinstance(b, TextBlock)]
                elif isinstance(mensaje, ResultMessage):
                    if mensaje.is_error:
                        return f"Algo ha fallado al consultar a Claude ({mensaje.subtype})."
                    if mensaje.result:
                        return mensaje.result.strip()
        return " ".join(p.strip() for p in partes if p.strip()) or "..."

    async def _conectar(self):
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        servidor = _servidor_mcp(self.herramientas)
        nombres = [f"mcp__{SERVIDOR}__{d['name']}" for d in self.herramientas.definiciones()]
        # Sin clave en el entorno, Claude Code usa la sesión de tu suscripción.
        os.environ.pop("ANTHROPIC_API_KEY", None)
        opciones = ClaudeAgentOptions(
            system_prompt=INSTRUCCIONES.format(nombre=self.config.nombre_usuario),
            model=self.config.modelo,
            effort=self.config.esfuerzo,
            tools=[],  # sin terminal ni edición de archivos: solo las herramientas de Jarvis
            mcp_servers={SERVIDOR: servidor},
            allowed_tools=nombres,
            permission_mode="dontAsk",
            setting_sources=[],  # no cargar ajustes, memoria ni skills de tu Claude Code
            max_turns=MAX_VUELTAS,
            cwd=str(self.config.carpeta_datos),
        )
        self.config.carpeta_datos.mkdir(parents=True, exist_ok=True)
        cliente = ClaudeSDKClient(opciones)
        await cliente.connect()
        return cliente


def _servidor_mcp(herramientas: Herramientas):
    """Convierte las herramientas de Jarvis en un servidor MCP dentro del proceso."""
    from claude_agent_sdk import create_sdk_mcp_server

    return create_sdk_mcp_server(name=SERVIDOR, tools=_herramientas_sdk(herramientas))


def _herramientas_sdk(herramientas: Herramientas) -> list:
    from claude_agent_sdk import tool

    def envolver(nombre: str):
        async def ejecutar(argumentos: dict[str, Any]) -> dict[str, Any]:
            salida, es_error = herramientas.ejecutar(nombre, argumentos)
            return {"content": [{"type": "text", "text": salida}], "is_error": es_error}
        return ejecutar

    return [
        tool(d["name"], d["description"], d["input_schema"])(envolver(d["name"]))
        for d in herramientas.definiciones()
    ]
