"""Habilidades propias de Jarvis: procedimientos en texto plano que el
propio Jarvis escribe para sí mismo cuando descubre una forma útil de hacer
algo — al estilo de un archivo de skill (SKILL.md), NUNCA código ejecutable.
Viven en ``~/.jarvis/habilidades/<slug>.md``.

Carga en dos niveles, igual que las skills de Claude Code: el system prompt
(ver cerebro._contexto_habilidades) solo lista nombre + descripción de cada
una; el procedimiento completo se lee bajo demanda con la herramienta
"leer_habilidad", para no inflar cada prompt con contenido que tal vez no
haga falta en este turno.
"""

from __future__ import annotations

import re
from pathlib import Path

_SLUG_INVALIDO = re.compile(r"[^a-z0-9-]+")
_SEPARADOR = "\n---\n"
LARGO_MAXIMO_NOMBRE = 60
LARGO_MAXIMO_DESCRIPCION = 200
LARGO_MAXIMO_CONTENIDO = 4000


def slug_seguro(nombre: str) -> str:
    """Nombre de archivo seguro a partir de lo que pida guardar el modelo:
    solo minúsculas, dígitos y guiones. Cualquier otro carácter (incluidos
    "/" y "..", que podrían escapar la carpeta de habilidades) se reemplaza
    por un guion — nunca se deja pasar tal cual."""
    slug = _SLUG_INVALIDO.sub("-", nombre.strip().lower()).strip("-")
    if not slug:
        raise ValueError("ese nombre no sirve como nombre de habilidad")
    return slug[:LARGO_MAXIMO_NOMBRE]


def ruta_habilidad(carpeta: Path, nombre: str) -> Path:
    return carpeta / f"{slug_seguro(nombre)}.md"


def guardar_habilidad(carpeta: Path, nombre: str, descripcion: str, contenido: str) -> Path:
    descripcion = descripcion.strip()
    contenido = contenido.strip()
    if not descripcion or len(descripcion) > LARGO_MAXIMO_DESCRIPCION or "\n" in descripcion:
        raise ValueError(
            f"la descripción tiene que ser una sola línea de hasta {LARGO_MAXIMO_DESCRIPCION} caracteres"
        )
    if not contenido:
        raise ValueError("decime el procedimiento de esta habilidad")
    if len(contenido) > LARGO_MAXIMO_CONTENIDO:
        raise ValueError(f"habilidad demasiado larga (máximo {LARGO_MAXIMO_CONTENIDO} caracteres)")
    ruta = ruta_habilidad(carpeta, nombre)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta.write_text(f"{descripcion}{_SEPARADOR}{contenido}\n", encoding="utf-8")
    return ruta


def listar_habilidades(carpeta: Path) -> list[tuple[str, str]]:
    """[(nombre, descripcion), ...] de cada habilidad guardada, por nombre."""
    if not carpeta.is_dir():
        return []
    resultado = []
    for ruta in sorted(carpeta.glob("*.md")):
        descripcion, _contenido = _separar(ruta.read_text(encoding="utf-8"))
        resultado.append((ruta.stem, descripcion))
    return resultado


def leer_habilidad(carpeta: Path, nombre: str) -> str:
    ruta = ruta_habilidad(carpeta, nombre)
    if not ruta.is_file():
        raise ValueError(f"no tengo ninguna habilidad guardada como «{nombre}»")
    _descripcion, contenido = _separar(ruta.read_text(encoding="utf-8"))
    return contenido


def _separar(texto: str) -> tuple[str, str]:
    if _SEPARADOR in texto:
        descripcion, contenido = texto.split(_SEPARADOR, 1)
        return descripcion.strip(), contenido.strip()
    return "", texto.strip()  # archivo con formato inesperado: todo cuenta como contenido
