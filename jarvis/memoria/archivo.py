"""Archivo frío de la memoria permanente: control de crecimiento del grafo
activo.

Diseño (ver README de la tarea / discusión con el usuario):

- El grafo activo (ladybug/kuzu) solo guarda hechos vigentes + invalidados
  recientes (ventana de gracia). Lo viejo se saca de ahí (lo hace
  ``adaptador_graphiti.AdaptadorMemoriaGraphiti.archivar``) y llega aquí.
- Chunks de TAMAÑO FIJO (no por calendario): se sigue escribiendo en el
  mismo ``archivo-NNNN.jsonl.gz`` hasta superar ``tamano_chunk_bytes``;
  entonces se abre un chunk nuevo. Formato JSON Lines comprimido con gzip.
- Manifiesto chico (``archivo-manifiesto.json``): por chunk, rango de
  fechas y un índice invertido tema/entidad → lista de chunks. Las
  entidades ya las extrajo graphiti al crear cada hecho (vienen en cada
  registro); aquí no se vuelve a procesar texto para sacarlas.
- Búsqueda en frío en dos pasos: 1) filtra candidatos por el índice
  invertido del manifiesto, sin descomprimir nada; 2) descomprime solo esos
  pocos chunks candidatos y re-embebe sus hechos al vuelo (no se guardan
  embeddings persistentes en frío) para rankear por similitud coseno.
"""

from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

NOMBRE_MANIFIESTO = "archivo-manifiesto.json"
TAMANO_CHUNK_BYTES_DEFECTO = 512 * 1024
PREFIJO_CHUNK = "archivo-"
SUFIJO_CHUNK = ".jsonl.gz"


@dataclass
class _Chunk:
    archivo: str
    desde: str
    hasta: str
    registros: int
    bytes: int


@dataclass
class Manifiesto:
    """Metadatos chicos del archivo frío: nunca hay que descomprimir nada
    para leer esto."""

    chunks: list[_Chunk] = field(default_factory=list)
    # entidad/tema (normalizado, minúsculas) -> lista de nombres de chunk
    indice_invertido: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def cargar(cls, ruta: Path) -> "Manifiesto":
        if not ruta.is_file():
            return cls()
        datos = json.loads(ruta.read_text("utf-8"))
        return cls(
            chunks=[_Chunk(**c) for c in datos.get("chunks", [])],
            indice_invertido=datos.get("indice_invertido", {}),
        )

    def guardar(self, ruta: Path) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = {
            "chunks": [vars(c) for c in self.chunks],
            "indice_invertido": self.indice_invertido,
        }
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), "utf-8")

    def _ultimo_chunk(self) -> _Chunk | None:
        return self.chunks[-1] if self.chunks else None

    def _agregar_al_indice(self, entidades: list[str], nombre_chunk: str) -> None:
        for entidad in entidades:
            clave = entidad.strip().lower()
            if not clave:
                continue
            archivos = self.indice_invertido.setdefault(clave, [])
            if nombre_chunk not in archivos:
                archivos.append(nombre_chunk)


def _ruta_manifiesto(carpeta: Path) -> Path:
    return carpeta / NOMBRE_MANIFIESTO


def _ruta_chunk(carpeta: Path, nombre: str) -> Path:
    return carpeta / nombre


def _siguiente_nombre_chunk(manifiesto: Manifiesto) -> str:
    numero = len(manifiesto.chunks) + 1
    return f"{PREFIJO_CHUNK}{numero:04d}{SUFIJO_CHUNK}"


def agregar_registros(
    carpeta: Path,
    registros: list[dict[str, Any]],
    tamano_chunk_bytes: int = TAMANO_CHUNK_BYTES_DEFECTO,
) -> Manifiesto:
    """Agrega ``registros`` (cada uno con al menos ``fecha`` ISO-8601 y
    ``entidades: list[str]``) al archivo frío, abriendo un chunk nuevo
    cuando el actual (de existir) ya supera ``tamano_chunk_bytes``.

    Devuelve el manifiesto actualizado (ya guardado en disco)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    manifiesto = Manifiesto.cargar(_ruta_manifiesto(carpeta))
    if not registros:
        return manifiesto

    ultimo = manifiesto._ultimo_chunk()
    abrir_nuevo = ultimo is None or ultimo.bytes >= tamano_chunk_bytes
    if abrir_nuevo:
        nombre_chunk = _siguiente_nombre_chunk(manifiesto)
        chunk = _Chunk(archivo=nombre_chunk, desde=registros[0]["fecha"], hasta=registros[0]["fecha"], registros=0, bytes=0)
        manifiesto.chunks.append(chunk)
    else:
        chunk = ultimo
        nombre_chunk = chunk.archivo

    ruta_chunk = _ruta_chunk(carpeta, nombre_chunk)
    modo = "ab" if ruta_chunk.is_file() else "wb"
    with gzip.open(ruta_chunk, modo) as archivo_gz:
        for registro in registros:
            linea = (json.dumps(registro, ensure_ascii=False) + "\n").encode("utf-8")
            archivo_gz.write(linea)
            chunk.registros += 1
            chunk.bytes += len(linea)
            fecha = registro["fecha"]
            chunk.desde = min(chunk.desde, fecha)
            chunk.hasta = max(chunk.hasta, fecha)
            manifiesto._agregar_al_indice(registro.get("entidades", []), nombre_chunk)

            # Si el chunk actual se llenó a mitad de la lista, cerrarlo y
            # abrir uno nuevo para los registros que falten (tamaño fijo,
            # no calendario: un lote grande puede repartirse en varios).
            if chunk.bytes >= tamano_chunk_bytes and registro is not registros[-1]:
                nombre_chunk = _siguiente_nombre_chunk(manifiesto)
                chunk = _Chunk(archivo=nombre_chunk, desde=fecha, hasta=fecha, registros=0, bytes=0)
                manifiesto.chunks.append(chunk)

    manifiesto.guardar(_ruta_manifiesto(carpeta))
    return manifiesto


def _leer_chunk(carpeta: Path, nombre: str) -> list[dict[str, Any]]:
    ruta = _ruta_chunk(carpeta, nombre)
    if not ruta.is_file():
        return []
    with gzip.open(ruta, "rb") as archivo_gz:
        return [json.loads(linea) for linea in archivo_gz if linea.strip()]


def _candidatos_por_indice(manifiesto: Manifiesto, consulta: str) -> set[str]:
    """Paso 1: filtra chunks candidatos por el índice invertido del
    manifiesto, sin descomprimir nada."""
    consulta_normalizada = consulta.lower()
    candidatos: set[str] = set()
    for entidad, chunks in manifiesto.indice_invertido.items():
        if entidad in consulta_normalizada:
            candidatos.update(chunks)
    return candidatos


def _similitud_coseno(a: list[float], b: list[float]) -> float:
    producto = sum(x * y for x, y in zip(a, b))
    norma_a = math.sqrt(sum(x * x for x in a))
    norma_b = math.sqrt(sum(y * y for y in b))
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return producto / (norma_a * norma_b)


def buscar_en_frio(
    carpeta: Path,
    consulta: str,
    limite: int,
    embeber: Callable[[list[str]], list[list[float]]],
) -> list[tuple[str, float]]:
    """Camino de 2 pasos: 1) filtra candidatos por el índice invertido
    (sin descomprimir); 2) descomprime solo esos chunks, re-embebe sus
    hechos al vuelo con ``embeber`` (debe devolver un vector por texto, en
    el mismo orden) y rankea por similitud coseno contra la consulta.

    Si ningún chunk coincide por entidad (la consulta no menciona a nadie
    conocido del archivo), se degrada con gracia: revisa todos los chunks
    en lugar de no encontrar nada — el archivo frío es chico y poco
    frecuente de consultar, así que el costo es aceptable."""
    manifiesto = Manifiesto.cargar(_ruta_manifiesto(carpeta))
    if not manifiesto.chunks:
        return []

    candidatos = _candidatos_por_indice(manifiesto, consulta)
    if not candidatos:
        candidatos = {chunk.archivo for chunk in manifiesto.chunks}

    registros: list[dict[str, Any]] = []
    for nombre_chunk in candidatos:
        registros.extend(_leer_chunk(carpeta, nombre_chunk))
    if not registros:
        return []

    textos = [registro["fact"] for registro in registros]
    vectores = embeber(textos + [consulta])
    vector_consulta = vectores[-1]
    vectores_textos = vectores[:-1]

    puntuados = [
        (texto, _similitud_coseno(vector, vector_consulta))
        for texto, vector in zip(textos, vectores_textos)
    ]
    puntuados.sort(key=lambda item: item[1], reverse=True)
    return puntuados[:limite]
