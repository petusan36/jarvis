"""Pruebas del archivo frío (jarvis.memoria.archivo): chunking por tamaño
fijo, manifiesto con índice invertido y búsqueda en frío de 2 pasos. Todo
puro y rápido: sin graphiti, sin ladybug, sin Ollama."""

from __future__ import annotations

from jarvis.memoria import archivo


def _registro(fecha: str, fact: str, entidades: list[str]) -> dict:
    return {
        "uuid": fact,
        "fact": fact,
        "valid_at": fecha,
        "invalid_at": fecha,
        "created_at": fecha,
        "fecha": fecha,
        "entidades": entidades,
    }


def test_agregar_registros_crea_un_solo_chunk_si_entra(tmp_path):
    registros = [_registro("2024-01-01", "a gusta el rock", ["usuario"])]

    manifiesto = archivo.agregar_registros(tmp_path, registros, tamano_chunk_bytes=1024 * 1024)

    assert len(manifiesto.chunks) == 1
    assert manifiesto.chunks[0].registros == 1
    assert "usuario" in manifiesto.indice_invertido
    assert manifiesto.chunks[0].archivo in manifiesto.indice_invertido["usuario"]
    assert (tmp_path / archivo.NOMBRE_MANIFIESTO).is_file()
    assert (tmp_path / manifiesto.chunks[0].archivo).is_file()


def test_agregar_registros_abre_chunk_nuevo_al_superar_tamano(tmp_path):
    # Tamaño de chunk minúsculo: cada registro individual ya lo supera, así
    # que cada uno debería terminar en su propio chunk.
    registros = [
        _registro("2024-01-01", "hecho uno bastante largo para pesar", ["tema-a"]),
        _registro("2024-02-01", "hecho dos bastante largo para pesar", ["tema-b"]),
        _registro("2024-03-01", "hecho tres bastante largo para pesar", ["tema-a"]),
    ]

    manifiesto = archivo.agregar_registros(tmp_path, registros, tamano_chunk_bytes=10)

    assert len(manifiesto.chunks) == 3
    nombres = {c.archivo for c in manifiesto.chunks}
    assert len(nombres) == 3
    # tema-a aparece en dos chunks distintos (registros 1 y 3).
    assert len(manifiesto.indice_invertido["tema-a"]) == 2
    assert len(manifiesto.indice_invertido["tema-b"]) == 1


def test_agregar_registros_sigue_llenando_el_ultimo_chunk_si_no_supero(tmp_path):
    archivo.agregar_registros(tmp_path, [_registro("2024-01-01", "primero", ["x"])], tamano_chunk_bytes=1024 * 1024)
    manifiesto = archivo.agregar_registros(
        tmp_path, [_registro("2024-01-02", "segundo", ["y"])], tamano_chunk_bytes=1024 * 1024
    )

    assert len(manifiesto.chunks) == 1
    assert manifiesto.chunks[0].registros == 2
    assert manifiesto.chunks[0].desde == "2024-01-01"
    assert manifiesto.chunks[0].hasta == "2024-01-02"


def test_agregar_registros_con_lista_vacia_no_crea_nada(tmp_path):
    manifiesto = archivo.agregar_registros(tmp_path, [], tamano_chunk_bytes=1024)
    assert manifiesto.chunks == []
    assert not (tmp_path / archivo.NOMBRE_MANIFIESTO).is_file()


def test_manifiesto_cargar_de_carpeta_vacia_no_rompe(tmp_path):
    manifiesto = archivo.Manifiesto.cargar(tmp_path / "no-existe.json")
    assert manifiesto.chunks == []
    assert manifiesto.indice_invertido == {}


def _embeber_falso(palabras_clave: dict[str, list[float]]):
    """Fábrica de un ``embeber`` determinístico para pruebas: cada texto se
    vectoriza según cuántas palabras clave contiene."""

    def embeber(textos: list[str]) -> list[list[float]]:
        vectores = []
        for texto in textos:
            texto_norm = texto.lower()
            vectores.append([1.0 if clave in texto_norm else 0.0 for clave in palabras_clave])
        return vectores

    return embeber


def test_buscar_en_frio_filtra_por_indice_invertido_y_rankea(tmp_path):
    registros = [
        _registro("2023-01-01", "le gustaba el rock hace mucho", ["musica"]),
        _registro("2023-02-01", "vivia en cordoba", ["ciudad"]),
    ]
    archivo.agregar_registros(tmp_path, registros, tamano_chunk_bytes=1024 * 1024)

    embeber = _embeber_falso({"rock": None, "cordoba": None})
    resultados = archivo.buscar_en_frio(tmp_path, "que rock le gustaba hace mucho", 5, embeber)

    assert resultados
    mejor_texto, mejor_puntaje = resultados[0]
    assert "rock" in mejor_texto
    assert mejor_puntaje > 0


def test_buscar_en_frio_sin_coincidencia_de_entidad_revisa_todo(tmp_path):
    registros = [_registro("2023-01-01", "le gustaba el rock", ["musica"])]
    archivo.agregar_registros(tmp_path, registros, tamano_chunk_bytes=1024 * 1024)

    llamadas = []

    def embeber(textos: list[str]) -> list[list[float]]:
        llamadas.append(list(textos))
        return [[1.0, 0.0] for _ in textos]

    resultados = archivo.buscar_en_frio(tmp_path, "algo que no menciona ninguna entidad conocida", 5, embeber)

    assert llamadas  # se llegó a embeber pese a no matchear el índice
    assert resultados


def test_buscar_en_frio_sin_chunks_devuelve_vacio(tmp_path):
    resultados = archivo.buscar_en_frio(tmp_path, "lo que sea", 5, lambda textos: [[0.0] for _ in textos])
    assert resultados == []
