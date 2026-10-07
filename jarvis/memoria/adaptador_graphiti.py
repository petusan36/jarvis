"""Adaptador de memoria permanente: graphiti-core (grafo de conocimiento
temporal) + ladybug (ex-Kuzu, grafo embebido en archivo, sin servidor) +
Ollama (LLM de extracción de entidades y embeddings, sin clave de API).

Descubrimiento no obvio (dejar documentado, no es evidente desde los docs
públicos de graphiti-core 0.30.2): su driver de Kuzu hace ``import kuzu``
a secas. El paquete que hay que instalar en PyPI para tener ese backend
—ya no se llama "kuzu" (proyecto discontinuado) sino "ladybug"
(LadybugDB, MIT, mismo equipo, API compatible: ``Database``, ``Connection``,
``AsyncConnection``...)— se importa como ``ladybug``, no como ``kuzu``. Sin
el alias de abajo, ``from graphiti_core.driver.kuzu_driver import
KuzuDriver`` falla con ``ModuleNotFoundError: No module named 'kuzu'``
aunque ``ladybug`` esté instalado. El alias se registra en
``sys.modules`` ANTES de importar ``kuzu_driver`` (que es quien hace el
``import kuzu`` real).

Conexión con Ollama sin clave de API: Ollama expone un endpoint compatible
con la API de chat/completions y de embeddings de OpenAI en
``http://localhost:11434/v1``. Se usa el cliente genérico de graphiti
(``OpenAIGenericClient`` / ``OpenAIEmbedder``) apuntando ahí, con una
``api_key`` cualquiera (Ollama no la valida, pero el SDK de OpenAI exige
que el campo no esté vacío). ``structured_output_mode="json_object"``
porque el soporte de ``json_schema`` (decodificación restringida) en el
servidor OpenAI-compatible de Ollama es irregular según el modelo; en modo
``json_object`` graphiti inyecta el esquema en el prompt en lugar de
exigirlo por API, más tolerante con un LLM local.

El re-ranker (cross-encoder) por defecto de graphiti (``OpenAIRerankerClient``)
usa log-probabilidades de un endpoint de completions que Ollama no expone
de forma confiable para todos los modelos. Para no depender de eso, este
adaptador usa un re-ranker local por superposición de palabras
(``_RerankerLocal``): no es tan preciso como un cross-encoder real, pero no
agrega una dependencia de red ni de un modelo adicional, y el ranking fino
de la lista corta de resultados de graphiti no es crítico para esta tarea
(el filtrado principal ya lo hace la búsqueda híbrida de graphiti).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .archivo import agregar_registros, buscar_en_frio
from .puerto import PuertoMemoria

MODELO_LLM_DEFECTO = "qwen3:8b"
MODELO_EMBEDDING_DEFECTO = "nomic-embed-text"
DIMENSION_EMBEDDING_NOMIC = 768
GRUPO_DEFECTO = "usuario"
VENTANA_GRACIA_DIAS_DEFECTO = 180

# Lenguaje temporal que sugiere que la respuesta puede estar solo en el
# archivo frío (hechos ya invalidados hace tiempo), aunque el grafo activo
# sí devuelva algo: en ese caso conviene revisar también el archivo frío.
_PISTAS_TEMPORALES = (
    "hace mucho", "hace tiempo", "hace años", "hace meses",
    "el año pasado", "antes", "anteriormente", "en el pasado", "antiguamente",
)


# Índices de texto completo (FTS) que graphiti-core espera encontrar ya
# creados al buscar (``edge_fulltext_search``, ``node_fulltext_search``...).
# Ver advertencia conocida en la tarea y docstring del módulo: el driver de
# Kuzu NO los crea solo (``build_indices_and_constraints`` es un no-op para
# este backend). Nombres y columnas verificados leyendo
# ``graphiti_core.search.search_utils`` (son los literales que esas
# funciones pasan a ``QUERY_FTS_INDEX``).
_INDICES_FTS = (
    ("Entity", "node_name_and_summary", ["name", "summary"]),
    ("RelatesToNode_", "edge_name_and_fact", ["name", "fact"]),
    ("Episodic", "episode_content", ["content"]),
    ("Community", "community_name", ["name"]),
)


def _crear_indices_fts(controlador: Any) -> None:
    """Crea a mano los índices de texto completo que
    ``KuzuDriver.build_indices_and_constraints`` no crea (ver advertencia
    conocida). Idempotente: si el índice ya existe, lo ignora."""
    import kuzu  # en este punto ya es el alias a ladybug (ver _asegurar_alias_kuzu)

    conexion = kuzu.Connection(controlador.db)
    try:
        conexion.execute("INSTALL FTS;")
        conexion.execute("LOAD EXTENSION FTS;")
        for tabla, nombre_indice, columnas in _INDICES_FTS:
            try:
                conexion.execute(
                    f"CALL CREATE_FTS_INDEX('{tabla}', '{nombre_indice}', {columnas});"
                )
            except RuntimeError as error:
                if "already exists" not in str(error):
                    raise
    finally:
        conexion.close()


def _asegurar_alias_kuzu() -> None:
    """Registra ``ladybug`` como ``kuzu`` en ``sys.modules`` si todavía no
    hay un ``kuzu`` real instalado. Ver docstring del módulo."""
    if "kuzu" not in sys.modules:
        try:
            import kuzu  # noqa: F401  (por si alguna vez hay un paquete "kuzu" real)
        except ImportError:
            import ladybug

            sys.modules["kuzu"] = ladybug


class _RerankerLocal:
    """Cross-encoder local, sin red: puntúa cada pasaje por superposición
    de palabras con la consulta. Ver docstring del módulo.

    No hereda de ``CrossEncoderClient`` en el cuerpo de la clase (evitaría
    importar ``graphiti_core.cross_encoder`` en el import perezoso de todo
    el módulo); se registra como subclase virtual en ``_asegurar_graphiti``
    con ``CrossEncoderClient.register`` — graphiti valida con
    ``isinstance`` (pydantic, modo ``is_instance_of``), que sí reconoce
    subclases virtuales de ``abc.ABC.register``."""

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        palabras_consulta = set(query.lower().split())
        puntuados = []
        for pasaje in passages:
            palabras_pasaje = set(pasaje.lower().split())
            if not palabras_consulta or not palabras_pasaje:
                puntuacion = 0.0
            else:
                interseccion = palabras_consulta & palabras_pasaje
                union = palabras_consulta | palabras_pasaje
                puntuacion = len(interseccion) / len(union)
            puntuados.append((pasaje, puntuacion))
        puntuados.sort(key=lambda item: item[1], reverse=True)
        return puntuados


def _tiene_lenguaje_temporal(consulta: str) -> bool:
    consulta_normalizada = consulta.lower()
    return any(pista in consulta_normalizada for pista in _PISTAS_TEMPORALES)


_CONSULTA_INVALIDADOS_VIEJOS = """
MATCH (origen:Entity)-[:RELATES_TO]->(r:RelatesToNode_)-[:RELATES_TO]->(destino:Entity)
WHERE r.group_id = $group_id AND r.invalid_at IS NOT NULL AND r.invalid_at < $corte
RETURN r.uuid AS uuid, r.fact AS fact, r.valid_at AS valid_at, r.invalid_at AS invalid_at,
       r.created_at AS created_at, origen.name AS origen, destino.name AS destino
"""


def _crear_clase_driver_kuzu_corregido():
    """Subclase de ``KuzuDriver`` que corrige un bug real encontrado en
    graphiti-core 0.30.2, verificado empíricamente contra el stack real
    (no documentado en ningún lado): ``KuzuDriver.execute_query`` descarta
    TODOS los parámetros con valor ``None`` antes de ejecutar la consulta
    (``params = {k: v for k, v in kwargs.items() if v is not None}``). Las
    plantillas de Cypher de graphiti para guardar una ``EntityEdge``
    siempre mencionan ``$invalid_at`` y ``$expired_at`` como parámetros
    —son ``None`` en cualquier hecho nuevo, todavía no invalidado—, así que
    CUALQUIER hecho nuevo con una relación real (no una Entity suelta)
    rompía con ``RuntimeError: Parameter invalid_at not found`` al
    guardarlo. Se verificó por separado que ladybug/kuzu sí acepta
    parámetros ``None`` (se bindean como ``NULL``) — el problema es solo
    que graphiti ni siquiera se los pasa. Esta subclase reimplementa
    ``execute_query`` igual que el original pero sin ese filtro."""
    from graphiti_core.driver.kuzu_driver import KuzuDriver, logger as logger_kuzu

    class _KuzuDriverLadybug(KuzuDriver):
        async def execute_query(self, cypher_query_: str, **kwargs: Any):
            params = dict(kwargs)
            params.pop("database_", None)
            params.pop("routing_", None)

            try:
                results = await self.client.execute(cypher_query_, parameters=params)
            except Exception as error:
                params_log = {k: (v[:5] if isinstance(v, list) else v) for k, v in params.items()}
                logger_kuzu.error(f"Error executing Kuzu query: {error}\n{cypher_query_}\n{params_log}")
                raise

            if not results:
                return [], None, None
            if isinstance(results, list):
                dict_results = [list(resultado.rows_as_dict()) for resultado in results]
            else:
                dict_results = list(results.rows_as_dict())
            return dict_results, None, None

    return _KuzuDriverLadybug


class AdaptadorMemoriaGraphiti(PuertoMemoria):
    """Implementación de ``PuertoMemoria`` con graphiti-core + ladybug +
    Ollama, con retención (grafo activo acotado + archivo frío por tamaño
    fijo + manifiesto con índice invertido + búsqueda en frío de 2 pasos).

    Las dependencias pesadas (graphiti, ladybug, el cliente de Ollama) se
    cargan de forma perezosa, al primer uso real, no al construir el
    adaptador: así ``Cerebro`` puede instanciarlo sin pagar ese costo si la
    sesión no llega a usar memoria.
    """

    def __init__(
        self,
        carpeta: Path,
        *,
        ollama_url: str = "http://localhost:11434",
        modelo_llm: str = MODELO_LLM_DEFECTO,
        modelo_embedding: str = MODELO_EMBEDDING_DEFECTO,
        grupo_id: str = GRUPO_DEFECTO,
        ventana_gracia_dias: int = VENTANA_GRACIA_DIAS_DEFECTO,
        tamano_chunk_bytes: int = 512 * 1024,
    ):
        self.carpeta = Path(carpeta)
        self.ollama_url = ollama_url.rstrip("/")
        self.modelo_llm = modelo_llm
        self.modelo_embedding = modelo_embedding
        self.grupo_id = grupo_id
        self.ventana_gracia_dias = ventana_gracia_dias
        self.tamano_chunk_bytes = tamano_chunk_bytes

        # Mismo patrón que ``CerebroSuscripcion``: un bucle de eventos propio
        # para poder exponer una API síncrona (la que espera ``Herramientas``
        # y ``Cerebro``) sobre una librería que es async-only.
        self._bucle = asyncio.new_event_loop()
        self._graphiti: Any = None
        self._embebedor: Any = None

    # --- construcción perezosa ------------------------------------------

    def _asegurar_graphiti(self) -> Any:
        if self._graphiti is not None:
            return self._graphiti

        _asegurar_alias_kuzu()
        from graphiti_core import Graphiti
        from graphiti_core.cross_encoder.client import CrossEncoderClient
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

        # Subclase virtual: graphiti valida con isinstance (pydantic), que sí
        # reconoce lo registrado vía abc.ABCMeta.register.
        CrossEncoderClient.register(_RerankerLocal)

        self.carpeta.mkdir(parents=True, exist_ok=True)
        ClaseDriverKuzu = _crear_clase_driver_kuzu_corregido()
        controlador = ClaseDriverKuzu(db=str(self.carpeta / "grafo.ladybug"))
        # Descubrimiento no obvio: graphiti-core 0.30.2 espera que todo
        # ``GraphDriver`` tenga el atributo ``_database`` (lo usa
        # ``Graphiti._resolve_request_scope`` para decidir si reutiliza el
        # driver o clona uno por group_id, ver graphiti.py). Neo4j/FalkorDB
        # lo setean en su ``__init__``; ``KuzuDriver`` (marcado deprecated
        # por el propio proyecto) no lo hace, y sin esto cualquier llamada
        # con ``group_id`` explícito revienta con
        # ``AttributeError: 'KuzuDriver' object has no attribute
        # '_database'``. Kuzu/ladybug es un único archivo embebido sin
        # noción real de "bases de datos" múltiples, así que fijarlo al
        # ``group_id`` que usamos siempre alcanza para que el driver se
        # reutilice en vez de intentar clonarse (que tampoco está bien
        # soportado en este backend).
        controlador._database = self.grupo_id
        _crear_indices_fts(controlador)

        cliente_llm = OpenAIGenericClient(
            config=LLMConfig(
                api_key="ollama",  # Ollama no valida la clave; el SDK exige que no esté vacía.
                model=self.modelo_llm,
                base_url=f"{self.ollama_url}/v1",
            ),
            # "json_schema" (decodificación restringida) en vez de
            # "json_object": verificado empíricamente que, con qwen3:8b en
            # Ollama 0.35, "json_object" (el esquema solo como texto en el
            # prompt) hace que el modelo a veces no respete la forma exacta
            # del esquema anidado de graphiti (ver notas en el adaptador),
            # mientras que "json_schema" lo fuerza por decodificación
            # restringida del propio servidor y no falló en las pruebas.
            structured_output_mode="json_schema",
        )
        self._embebedor = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key="ollama",
                embedding_model=self.modelo_embedding,
                embedding_dim=DIMENSION_EMBEDDING_NOMIC,
                base_url=f"{self.ollama_url}/v1",
            )
        )

        self._graphiti = Graphiti(
            graph_driver=controlador,
            llm_client=cliente_llm,
            embedder=self._embebedor,
            cross_encoder=_RerankerLocal(),
        )
        # No-op para Kuzu (ver advertencia conocida: su driver no crea
        # índices full-text solo), pero se llama igual por si una versión
        # futura del driver sí lo implementa.
        self._bucle.run_until_complete(self._graphiti.build_indices_and_constraints())
        return self._graphiti

    def _embeber_sync(self, textos: list[str]) -> list[list[float]]:
        self._asegurar_graphiti()
        return self._bucle.run_until_complete(self._embebedor.create_batch(textos))

    # --- PuertoMemoria -----------------------------------------------------

    def recordar(self, hecho: str, valor: str) -> str:
        from graphiti_core.nodes import EpisodeType

        grafo = self._asegurar_graphiti()
        # Descubrimiento no obvio (verificado empíricamente, no documentado
        # en los ejemplos públicos de graphiti): un episodio como
        # "{hecho}: {valor}" (p. ej. "genero de musica preferido: rock")
        # NO alcanza. El extractor de entidades de graphiti solo encuentra
        # un nombre propio en ese texto ("rock") y no tiene con quién
        # relacionarlo, así que no crea ningún RELATES_TO (edge) — queda
        # como una Entity suelta, sin ``fact`` asociado, invisible para
        # ``search()`` y para la invalidación temporal (que es justamente
        # lo que está pensado para resolver "antes rock, después
        # baladas"). Hace falta una frase declarativa con un sujeto
        # explícito ("el usuario") para que la extracción produzca
        # (usuario)-[hecho]->(valor) con una ``fact`` de verdad.
        texto = f"El usuario dice que su {hecho} es: {valor}."
        self._bucle.run_until_complete(
            grafo.add_episode(
                name=hecho,
                episode_body=texto,
                source=EpisodeType.message,
                source_description="herramienta recordar",
                reference_time=datetime.now(timezone.utc),
                group_id=self.grupo_id,
            )
        )
        return f"Guardado en memoria: {hecho}: {valor}"

    def contexto_relevante(self, consulta: str, limite: int = 5) -> list[str]:
        grafo = self._asegurar_graphiti()
        resultados = self._bucle.run_until_complete(
            grafo.search(consulta, group_ids=[self.grupo_id], num_results=limite)
        )
        hechos = [borde.fact for borde in resultados]

        necesita_frio = not hechos or _tiene_lenguaje_temporal(consulta)
        if not necesita_frio:
            return hechos

        frios = buscar_en_frio(self.carpeta, consulta, limite, self._embeber_sync)
        for texto, _puntuacion in frios:
            if texto not in hechos:
                hechos.append(texto)
        return hechos[:limite]

    def archivar(self, ahora: datetime | None = None) -> int:
        grafo = self._asegurar_graphiti()
        ahora = ahora or datetime.now(timezone.utc)
        corte = ahora - timedelta(days=self.ventana_gracia_dias)

        filas, _, _ = self._bucle.run_until_complete(
            grafo.driver.execute_query(
                _CONSULTA_INVALIDADOS_VIEJOS, group_id=self.grupo_id, corte=corte
            )
        )
        if not filas:
            return 0

        registros = [
            {
                "uuid": fila["uuid"],
                "fact": fila["fact"],
                "valid_at": _a_iso(fila.get("valid_at")),
                "invalid_at": _a_iso(fila.get("invalid_at")),
                "created_at": _a_iso(fila.get("created_at")),
                "fecha": _a_iso(fila.get("invalid_at")) or _a_iso(fila.get("created_at")),
                "entidades": [e for e in (fila.get("origen"), fila.get("destino")) if e],
            }
            for fila in filas
        ]
        agregar_registros(self.carpeta, registros, self.tamano_chunk_bytes)

        from graphiti_core.edges import EntityEdge

        uuids = [registro["uuid"] for registro in registros]
        self._bucle.run_until_complete(EntityEdge.delete_by_uuids(grafo.driver, uuids))
        return len(registros)

    def cerrar(self) -> None:
        if self._graphiti is not None:
            self._bucle.run_until_complete(self._graphiti.close())
        self._bucle.close()


def _a_iso(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.isoformat()
    return str(valor)
