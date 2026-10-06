"""Memoria permanente de Jarvis: hechos sobre el usuario que persisten entre
sesiones, se actualizan sin quedar contradictorios (ventana de validez
temporal) y escalan sin crecer sin control (archivado en frío).

``Cerebro`` (y la herramienta ``recordar``, ver ``jarvis.herramientas``) solo
conocen ``PuertoMemoria``: no saben nada de graphiti, ladybug ni ollama. El
adaptador concreto vive en ``adaptador_graphiti.py`` y se importa de forma
perezosa (las dependencias pesadas no se cargan si la memoria está
deshabilitada o en tests que no la ejercitan).
"""

from __future__ import annotations

from .puerto import PuertoMemoria

__all__ = ["PuertoMemoria"]


def __getattr__(nombre: str):  # pragma: no cover - import perezoso trivial
    if nombre == "AdaptadorMemoriaGraphiti":
        from .adaptador_graphiti import AdaptadorMemoriaGraphiti

        return AdaptadorMemoriaGraphiti
    raise AttributeError(nombre)
