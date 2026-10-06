"""El cerebro de Jarvis: conversa con un proveedor de IA (puerto
``ProveedorIA``) y ejecuta las herramientas que pida.

No conoce anthropic, openai ni ollama: solo el puerto, inyectado por quien
construye el ``Cerebro`` (ver ``jarvis.proveedores`` y ``jarvis.__main__``).
"""

from __future__ import annotations

from typing import Any

from .config import Config
from .herramientas import Herramientas
from .proveedores import (
    AdaptadorAnthropic,
    BloqueTexto,
    BloqueUsoHerramienta,
    ProveedorIA,
    ResultadoHerramienta,
    TurnoAsistente,
    TurnoResultadoHerramienta,
    TurnoUsuario,
)

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
No puedes borrar ni mover archivos: si te lo piden, explica que no tienes permiso.
- Si una herramienta funciona a medias por falta de configuración (por ejemplo, una \
clave de API ausente), no te limites a informarlo: proponele a {nombre} que la agregue \
y ofrecele explicarle cómo conseguirla, para que la próxima vez funcione completo."""

# Límite de vueltas herramienta→respuesta por mensaje, por si algo entra en bucle.
MAX_VUELTAS = 10


class Cerebro:
    def __init__(self, config: Config, herramientas: Herramientas, proveedor: ProveedorIA | None = None):
        self.config = config
        self.herramientas = herramientas
        # Por defecto, Anthropic (comportamiento histórico de Jarvis).
        self.proveedor = proveedor or AdaptadorAnthropic()
        self.historial: list[Any] = []

    def responder(self, texto_usuario: str) -> str:
        """Envía un mensaje del usuario y devuelve la respuesta final en texto."""
        self.herramientas.nuevo_turno()
        self.historial.append(TurnoUsuario(texto=texto_usuario))

        for _ in range(MAX_VUELTAS):
            respuesta = self.proveedor.responder(
                mensajes=self.historial,
                sistema=INSTRUCCIONES.format(nombre=self.config.nombre_usuario),
                herramientas=self.herramientas.definiciones(),
                modelo=self.config.modelo,
                max_tokens=self.config.max_tokens,
                esfuerzo=self.config.esfuerzo,
            )
            # Se guarda el contenido completo (incluido ``bruto``, con cualquier
            # bloque de razonamiento) para que la conversación siga siendo
            # válida en la siguiente vuelta.
            self.historial.append(TurnoAsistente(contenido=respuesta.contenido, bruto=respuesta.bruto))

            if respuesta.detenida_por == "rechazo":
                return "Me temo que no puedo ayudarle con eso."
            if respuesta.detenida_por != "herramienta":
                texto = _texto(respuesta.contenido)
                if respuesta.detenida_por == "longitud":
                    texto += " (respuesta cortada por longitud)"
                return texto or "..."

            resultados = []
            for bloque in respuesta.contenido:
                if not isinstance(bloque, BloqueUsoHerramienta):
                    continue
                salida, es_error = self.herramientas.ejecutar(bloque.nombre, bloque.entrada)
                resultados.append(ResultadoHerramienta(id_uso=bloque.id, contenido=salida, es_error=es_error))
            # Todos los resultados van juntos en un único turno.
            self.historial.append(TurnoResultadoHerramienta(resultados=resultados))

        return "He dado demasiadas vueltas a esto. ¿Podría reformular la petición?"

    def olvidar(self) -> None:
        """Empieza una conversación nueva."""
        self.historial.clear()


def _texto(contenido: list[Any]) -> str:
    return "".join(b.texto for b in contenido if isinstance(b, BloqueTexto)).strip()
