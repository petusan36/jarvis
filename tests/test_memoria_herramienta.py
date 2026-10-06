"""La herramienta "recordar" y la inyección de contexto de memoria en
Cerebro, contra un ``PuertoMemoria`` falso: no tocan graphiti/ladybug/ollama."""

from __future__ import annotations

from jarvis.cerebro import _contexto_memoria
from jarvis.herramientas import Herramientas
from jarvis.memoria.puerto import PuertoMemoria


class _MemoriaFalsa(PuertoMemoria):
    def __init__(self, hechos: list[str] | None = None):
        self.hechos = hechos or []
        self.guardados: list[tuple[str, str]] = []

    def recordar(self, hecho: str, valor: str) -> str:
        self.guardados.append((hecho, valor))
        return f"Guardado en memoria: {hecho}: {valor}"

    def contexto_relevante(self, consulta: str, limite: int = 5) -> list[str]:
        return self.hechos[:limite]

    def archivar(self, ahora=None) -> int:
        return 0


def test_sin_memoria_no_registra_la_herramienta(tmp_path):
    h = Herramientas(tmp_path, sistema=False)
    assert "recordar" not in {d["name"] for d in h.definiciones()}
    assert h.memoria is None


def test_con_memoria_registra_recordar_y_delega(tmp_path):
    memoria = _MemoriaFalsa()
    h = Herramientas(tmp_path, sistema=False, memoria=memoria)

    assert "recordar" in {d["name"] for d in h.definiciones()}

    salida, es_error = h.ejecutar(
        "recordar", {"hecho": "genero de musica preferido", "valor": "rock"}
    )

    assert not es_error
    assert "rock" in salida
    assert memoria.guardados == [("genero de musica preferido", "rock")]


def test_contexto_memoria_vacio_sin_memoria():
    assert _contexto_memoria(None, "cualquier cosa") == ""


def test_contexto_memoria_vacio_sin_hechos_relevantes():
    memoria = _MemoriaFalsa(hechos=[])
    assert _contexto_memoria(memoria, "cualquier cosa") == ""


def test_contexto_memoria_incluye_los_hechos_encontrados():
    memoria = _MemoriaFalsa(hechos=["le gusta el rock", "vive en Córdoba"])

    contexto = _contexto_memoria(memoria, "que le gusta")

    assert "le gusta el rock" in contexto
    assert "vive en Córdoba" in contexto
    assert contexto.startswith("\n\n")
