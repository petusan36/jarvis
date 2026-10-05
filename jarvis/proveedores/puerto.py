"""Puerto (interfaz) que todo proveedor de IA debe implementar.

``Cerebro`` solo conoce esta interfaz y los tipos de este módulo: no sabe
nada de anthropic ni de ollama. Cada proveedor vive en su propio adaptador
(ver ``anthropic_adaptador.py`` y ``ollama_adaptador.py``) y traduce entre
este formato neutral y el formato nativo de su API, incluyendo el de las
herramientas (tool-calling).

El historial de la conversación (``Cerebro.historial``) se guarda en estos
mismos tipos neutrales (``TurnoUsuario``, ``TurnoAsistente``,
``TurnoResultadoHerramienta``). Cada ``TurnoAsistente`` lleva, además de su
vista normalizada (``contenido``, la que usa ``Cerebro`` para decidir qué
hacer), un campo ``bruto`` con la representación nativa que devolvió el
proveedor (incluido cualquier bloque de razonamiento). El adaptador se la
reenvía intacta en la vuelta siguiente, para no perder contexto ni romper
una conversación en curso — tal como hacía el código original con los
bloques de contenido de Anthropic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Union


@dataclass
class BloqueTexto:
    """Fragmento de texto normal dentro de una respuesta del modelo."""

    texto: str


@dataclass
class BloqueUsoHerramienta:
    """Petición del modelo para ejecutar una herramienta."""

    id: str
    nombre: str
    entrada: dict[str, Any]


BloqueContenido = Union[BloqueTexto, BloqueUsoHerramienta]


@dataclass
class ResultadoHerramienta:
    """Resultado de ejecutar una herramienta, listo para devolver al modelo."""

    id_uso: str
    contenido: str
    es_error: bool = False


@dataclass
class RespuestaIA:
    """Respuesta normalizada de una vuelta de conversación."""

    contenido: list[BloqueContenido]
    # "texto" | "herramienta" | "longitud" | "rechazo"
    detenida_por: str
    # Representación nativa del proveedor (p. ej. los bloques crudos que
    # devuelve Anthropic, con su razonamiento incluido). Si es None, el
    # adaptador reconstruye el mensaje a partir de ``contenido`` la próxima
    # vez que lo necesite.
    bruto: Any = None


@dataclass
class TurnoUsuario:
    """Un mensaje del usuario."""

    texto: str


@dataclass
class TurnoAsistente:
    """Una respuesta del modelo (ya guardada en el historial)."""

    contenido: list[BloqueContenido]
    bruto: Any = None


@dataclass
class TurnoResultadoHerramienta:
    """Los resultados de ejecutar una o más herramientas, en un solo turno."""

    resultados: list[ResultadoHerramienta]


Turno = Union[TurnoUsuario, TurnoAsistente, TurnoResultadoHerramienta]


class ProveedorIA(ABC):
    """Puerto abstracto para un proveedor de IA con tool-calling.

    ``Cerebro`` depende únicamente de esta interfaz (inyección de
    dependencia): no construye ni conoce clientes concretos de anthropic
    ni de ollama.
    """

    @abstractmethod
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
        """Envía una vuelta de conversación y devuelve la respuesta normalizada.

        - ``mensajes``: historial completo en formato neutral (ver ``Turno*``).
        - ``herramientas``: definiciones en el formato de tool-use de
          Anthropic (``name``, ``description``, ``input_schema``); cada
          adaptador las traduce a su propio formato de function-calling.
        - ``esfuerzo``: "low" | "medium" | "high". Los proveedores que no
          soporten este concepto pueden ignorarlo.
        """
