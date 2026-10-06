"""Puerto (interfaz) que toda implementación de memoria permanente debe
cumplir.

``Cerebro`` y la herramienta ``recordar`` dependen únicamente de esta
interfaz (inyección de dependencia), igual que ya hacen con ``ProveedorIA``
en ``jarvis.proveedores.puerto``: no construyen ni conocen clientes
concretos de graphiti, ladybug ni ollama.

Alcance de esta tarea (documentado a pedido): escribir o actualizar un hecho
en memoria es una herramienta explícita (``recordar``) que el modelo invoca
y que el usuario ve en la conversación — no ocurre nada automático ni oculto.
El mecanismo general de "pedir autorización antes de cualquier herramienta
nueva" (roadmap del proyecto) queda fuera de esta tarea.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class PuertoMemoria(ABC):
    """Memoria permanente: hechos sobre el usuario con validez temporal."""

    @abstractmethod
    def recordar(self, hecho: str, valor: str) -> str:
        """Guarda o actualiza un hecho. Si contradice uno anterior (por
        ejemplo, un cambio de preferencia), el anterior queda invalidado
        —no borrado ni dejado contradictorio— con su propia ventana de
        validez temporal."""

    @abstractmethod
    def contexto_relevante(self, consulta: str, limite: int = 5) -> list[str]:
        """Devuelve hasta ``limite`` hechos relevantes para ``consulta``,
        pensados para inyectarse en el prompt del sistema antes de responder.
        Busca primero en el grafo activo; si no encuentra nada útil (o la
        consulta usa lenguaje temporal como "hace mucho"), busca también en
        el archivo frío."""

    @abstractmethod
    def archivar(self, ahora: datetime | None = None) -> int:
        """Tarea de mantenimiento: saca del grafo activo los hechos
        invalidados que superan la ventana de gracia y los exporta al
        archivo frío. Devuelve cuántos hechos se archivaron."""
