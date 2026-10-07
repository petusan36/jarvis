"""Pruebas del adaptador graphiti/ladybug/ollama que no requieren un
Ollama real: lógica de archivado/retención con un ``Graphiti`` falso, el
alias de import kuzu->ladybug, el re-ranker local y la detección de
lenguaje temporal.

La prueba de integración real (guardar, actualizar sin contradicción,
archivar de verdad y buscar en frío) se corrió manualmente contra el stack
en esta máquina — ver el reporte de la tarea; no se automatiza aquí porque
tarda varios minutos por llamada al LLM local y requiere Ollama corriendo."""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from jarvis.memoria.adaptador_graphiti import (
    AdaptadorMemoriaGraphiti,
    _asegurar_alias_kuzu,
    _RerankerLocal,
    _tiene_lenguaje_temporal,
)


def test_tiene_lenguaje_temporal_detecta_pistas():
    assert _tiene_lenguaje_temporal("¿qué me gustaba hace mucho?")
    assert _tiene_lenguaje_temporal("el año pasado te conté algo")
    assert not _tiene_lenguaje_temporal("qué música me gusta ahora")


def test_reranker_local_puntua_por_superposicion_de_palabras():
    reranker = _RerankerLocal()
    resultados = asyncio.run(reranker.rank("musica rock", ["le gusta el rock", "vive en Córdoba"]))

    assert resultados[0][0] == "le gusta el rock"
    assert resultados[0][1] > resultados[1][1]


def test_asegurar_alias_kuzu_registra_ladybug_como_kuzu(monkeypatch):
    sys.modules.pop("kuzu", None)
    ladybug_falso = types.ModuleType("ladybug")
    monkeypatch.setitem(sys.modules, "ladybug", ladybug_falso)

    # Simula que no hay un paquete "kuzu" real instalado.
    import builtins

    importador_real = builtins.__import__

    def importador_falso(nombre, *args, **kwargs):
        if nombre == "kuzu":
            raise ImportError("sin kuzu real")
        return importador_real(nombre, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importador_falso)
    try:
        _asegurar_alias_kuzu()
    finally:
        monkeypatch.setattr(builtins, "__import__", importador_real)

    assert sys.modules["kuzu"] is ladybug_falso
    del sys.modules["kuzu"]


class _DriverFalso:
    def __init__(self, filas):
        self._filas = filas
        self.ultima_consulta = None
        self.ultimos_parametros = None

    async def execute_query(self, consulta, **parametros):
        self.ultima_consulta = consulta
        self.ultimos_parametros = parametros
        return self._filas, None, None


class _GraphitiFalso:
    def __init__(self, filas):
        self.driver = _DriverFalso(filas)


def test_archivar_exporta_y_borra_los_invalidados_viejos(tmp_path, monkeypatch):
    filas = [
        {
            "uuid": "u1",
            "fact": "genero de musica preferido: rock",
            "valid_at": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "invalid_at": datetime(2023, 6, 1, tzinfo=timezone.utc),
            "created_at": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "origen": "usuario",
            "destino": "rock",
        }
    ]
    adaptador = AdaptadorMemoriaGraphiti(tmp_path / "memoria", ventana_gracia_dias=1)
    adaptador._graphiti = _GraphitiFalso(filas)

    borrado_mock = AsyncMock()
    monkeypatch.setattr("graphiti_core.edges.EntityEdge.delete_by_uuids", borrado_mock)

    cantidad = adaptador.archivar(ahora=datetime(2024, 1, 1, tzinfo=timezone.utc))

    assert cantidad == 1
    borrado_mock.assert_awaited_once()
    args = borrado_mock.await_args.args
    assert args[1] == ["u1"]

    # El hecho quedó en el archivo frío.
    from jarvis.memoria.archivo import Manifiesto, _ruta_manifiesto

    manifiesto = Manifiesto.cargar(_ruta_manifiesto(tmp_path / "memoria"))
    assert len(manifiesto.chunks) == 1
    assert "usuario" in manifiesto.indice_invertido


def test_archivar_sin_invalidados_viejos_no_hace_nada(tmp_path, monkeypatch):
    adaptador = AdaptadorMemoriaGraphiti(tmp_path / "memoria", ventana_gracia_dias=180)
    adaptador._graphiti = _GraphitiFalso([])

    borrado_mock = AsyncMock()
    monkeypatch.setattr("graphiti_core.edges.EntityEdge.delete_by_uuids", borrado_mock)

    assert adaptador.archivar() == 0
    borrado_mock.assert_not_awaited()


def test_crear_indices_fts_es_idempotente_contra_ladybug_real(tmp_path):
    """Verificación real (sin Ollama, solo ladybug): la advertencia conocida
    de la tarea dice que el driver de Kuzu no crea solo los índices
    full-text. Esta prueba crea un ``KuzuDriver`` de verdad contra un
    archivo ``.ladybug`` temporal, crea los índices a mano dos veces (debe
    ser un no-op la segunda) y confirma que ``QUERY_FTS_INDEX`` ya no
    revienta con "function ... is not defined"."""
    _asegurar_alias_kuzu()
    from graphiti_core.driver.kuzu_driver import KuzuDriver

    from jarvis.memoria.adaptador_graphiti import _crear_indices_fts

    controlador = KuzuDriver(db=str(tmp_path / "grafo.ladybug"))
    _crear_indices_fts(controlador)
    _crear_indices_fts(controlador)  # segunda vez: no debe explotar

    import kuzu

    conexion = kuzu.Connection(controlador.db)
    try:
        resultado = conexion.execute(
            "CALL QUERY_FTS_INDEX('RelatesToNode_', 'edge_name_and_fact', 'rock', TOP := 5) "
            "RETURN node.uuid AS uuid;"
        )
        assert list(resultado.rows_as_dict()) == []  # sin datos todavía, pero no explota
    finally:
        conexion.close()
