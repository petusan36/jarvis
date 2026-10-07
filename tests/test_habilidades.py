"""Pruebas de jarvis.habilidades: guardar/leer/listar, y la sanitización de
nombre de archivo (slug_seguro) contra traversal de ruta."""

import pytest

from jarvis.habilidades import (
    LARGO_MAXIMO_CONTENIDO,
    LARGO_MAXIMO_DESCRIPCION,
    guardar_habilidad,
    leer_habilidad,
    listar_habilidades,
    ruta_habilidad,
    slug_seguro,
)


def test_slug_seguro_normaliza_nombre_simple():
    assert slug_seguro("Resumen PDF Largo") == "resumen-pdf-largo"


def test_slug_seguro_rechaza_traversal_de_ruta():
    """El nombre lo decide el modelo, no un path de confianza: "../../etc/passwd"
    nunca debe poder escapar la carpeta de habilidades."""
    assert "/" not in slug_seguro("../../etc/passwd")
    assert ".." not in slug_seguro("../../etc/passwd")


def test_slug_seguro_vacio_tras_sanitizar_falla():
    with pytest.raises(ValueError):
        slug_seguro("///...")


def test_slug_seguro_trunca_a_largo_maximo():
    largo = "a" * 200
    assert len(slug_seguro(largo)) <= 60


def test_guardar_y_leer_habilidad(tmp_path):
    carpeta = tmp_path / "habilidades"
    ruta = guardar_habilidad(carpeta, "Mi Habilidad", "Para qué sirve", "Paso 1\nPaso 2")

    assert ruta == ruta_habilidad(carpeta, "Mi Habilidad")
    assert ruta.is_file()
    assert leer_habilidad(carpeta, "mi-habilidad") == "Paso 1\nPaso 2"


def test_mejorar_habilidad_existente_la_reemplaza_entera(tmp_path):
    carpeta = tmp_path / "habilidades"
    guardar_habilidad(carpeta, "x", "primera versión", "contenido viejo")
    guardar_habilidad(carpeta, "x", "segunda versión", "contenido nuevo")

    assert leer_habilidad(carpeta, "x") == "contenido nuevo"
    assert listar_habilidades(carpeta) == [("x", "segunda versión")]


def test_listar_habilidades_sin_carpeta_devuelve_vacio(tmp_path):
    assert listar_habilidades(tmp_path / "no-existe") == []


def test_listar_habilidades_ordenadas_por_nombre(tmp_path):
    carpeta = tmp_path / "habilidades"
    guardar_habilidad(carpeta, "zeta", "última", "c")
    guardar_habilidad(carpeta, "alfa", "primera", "c")

    assert listar_habilidades(carpeta) == [("alfa", "primera"), ("zeta", "última")]


def test_leer_habilidad_inexistente_falla(tmp_path):
    with pytest.raises(ValueError):
        leer_habilidad(tmp_path / "habilidades", "no-existe")


def test_descripcion_vacia_falla(tmp_path):
    with pytest.raises(ValueError):
        guardar_habilidad(tmp_path / "habilidades", "x", "   ", "contenido")


def test_descripcion_con_salto_de_linea_falla(tmp_path):
    """La descripción se lista siempre en el system prompt (ver
    cerebro._contexto_habilidades): un salto de línea rompería ese listado
    (una línea por habilidad) y podría inyectar una entrada falsa."""
    with pytest.raises(ValueError):
        guardar_habilidad(tmp_path / "habilidades", "x", "línea 1\nlínea 2", "contenido")


def test_descripcion_demasiado_larga_falla(tmp_path):
    with pytest.raises(ValueError):
        guardar_habilidad(tmp_path / "habilidades", "x", "a" * (LARGO_MAXIMO_DESCRIPCION + 1), "contenido")


def test_contenido_vacio_falla(tmp_path):
    with pytest.raises(ValueError):
        guardar_habilidad(tmp_path / "habilidades", "x", "descripción", "   ")


def test_contenido_demasiado_largo_falla(tmp_path):
    with pytest.raises(ValueError):
        guardar_habilidad(tmp_path / "habilidades", "x", "descripción", "a" * (LARGO_MAXIMO_CONTENIDO + 1))


# --- cerebro._contexto_habilidades: lo que se anexa a INSTRUCCIONES --------

def test_contexto_habilidades_vacio_sin_ninguna_guardada(tmp_path):
    from jarvis.cerebro import _contexto_habilidades

    assert _contexto_habilidades(tmp_path) == ""


def test_contexto_habilidades_lista_nombre_y_descripcion_no_el_contenido(tmp_path):
    from jarvis.cerebro import _contexto_habilidades

    guardar_habilidad(tmp_path / "habilidades", "x", "para qué sirve", "procedimiento secreto, no debería salir")

    contexto = _contexto_habilidades(tmp_path)

    assert "para qué sirve" in contexto
    assert "procedimiento secreto" not in contexto  # solo bajo demanda, con leer_habilidad
