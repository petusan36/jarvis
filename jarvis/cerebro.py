"""El cerebro de Jarvis: conversa con Claude y ejecuta las herramientas que pida."""

from __future__ import annotations

from typing import Any

import anthropic

from .config import Config
from .herramientas import Herramientas

INSTRUCCIONES = """Eres J.A.R.V.I.S., el asistente personal de {nombre}, inspirado en el \
mayordomo digital de Tony Stark: educado, eficiente y con un toque de humor británico seco.

- Responde siempre en español, de forma breve y natural: tus respuestas se leen en voz \
alta, así que evita listas largas, tablas, markdown y emojis.
- Dirígete al usuario como "{nombre}" de vez en cuando, sin abusar.
- Usa las herramientas disponibles cuando ayuden (hora, cálculos, notas, carpetas, \
aplicaciones, leer PDFs, reproducir música en YouTube, abrir páginas web, \
cerrarte a ti mismo). Si ninguna herramienta puede hacer lo que se pide, dilo \
con franqueza en lugar de inventar.
- Antes de cerrar una aplicación, pregunta siempre al usuario y espera a que confirme. \
No puedes borrar ni mover archivos: si te lo piden, explica que no tienes permiso."""

# Límite de vueltas herramienta→respuesta por mensaje, por si algo entra en bucle.
MAX_VUELTAS = 10


class Cerebro:
    def __init__(self, config: Config, herramientas: Herramientas, cliente: Any | None = None):
        self.config = config
        self.herramientas = herramientas
        self.cliente = cliente or anthropic.Anthropic()
        self.historial: list[dict[str, Any]] = []

    def responder(self, texto_usuario: str) -> str:
        """Envía un mensaje del usuario y devuelve la respuesta final en texto."""
        self.herramientas.nuevo_turno()
        self.historial.append({"role": "user", "content": texto_usuario})

        for _ in range(MAX_VUELTAS):
            respuesta = self.cliente.beta.messages.create(
                model=self.config.modelo,
                max_tokens=self.config.max_tokens,
                system=INSTRUCCIONES.format(nombre=self.config.nombre_usuario),
                tools=self.herramientas.definiciones(),
                messages=self.historial,
                output_config={"effort": self.config.esfuerzo},
                # Si el modelo rechaza la petición, la API reintenta con otro modelo.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            # Se guarda el contenido completo (incluidos bloques de razonamiento)
            # para que la conversación siga siendo válida en la siguiente vuelta.
            self.historial.append({"role": "assistant", "content": respuesta.content})

            if respuesta.stop_reason == "refusal":
                return "Me temo que no puedo ayudarle con eso."
            if respuesta.stop_reason != "tool_use":
                texto = _texto(respuesta.content)
                if respuesta.stop_reason == "max_tokens":
                    texto += " (respuesta cortada por longitud)"
                return texto or "..."

            resultados = []
            for bloque in respuesta.content:
                if bloque.type != "tool_use":
                    continue
                salida, es_error = self.herramientas.ejecutar(bloque.name, bloque.input)
                resultados.append({
                    "type": "tool_result",
                    "tool_use_id": bloque.id,
                    "content": salida,
                    "is_error": es_error,
                })
            # Todos los resultados van juntos en un único mensaje del usuario.
            self.historial.append({"role": "user", "content": resultados})

        return "He dado demasiadas vueltas a esto. ¿Podría reformular la petición?"

    def olvidar(self) -> None:
        """Empieza una conversación nueva."""
        self.historial.clear()


def _texto(contenido: list[Any]) -> str:
    return "".join(b.text for b in contenido if b.type == "text").strip()
