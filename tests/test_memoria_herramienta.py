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


def test_recordar_sin_confirmar_queda_pendiente_y_no_escribe(tmp_path):
    """Gate de autorización: sin esto, una instrucción inyectada (ej. desde
    una página web que Jarvis lea) podría escribir en memoria permanente sin
    que el usuario lo viera ni lo aprobara."""
    memoria = _MemoriaFalsa()
    h = Herramientas(tmp_path, sistema=False, memoria=memoria)

    assert "recordar" in {d["name"] for d in h.definiciones()}

    salida, es_error = h.ejecutar(
        "recordar", {"hecho": "genero de musica preferido", "valor": "rock", "confirmado": False}
    )

    assert not es_error
    assert "pendiente" in salida.lower()
    assert memoria.guardados == []


def test_recordar_confirmado_en_mismo_turno_no_escribe(tmp_path):
    """Solo vale una confirmación dada en un mensaje POSTERIOR a la
    petición — igual que cerrar_aplicacion."""
    memoria = _MemoriaFalsa()
    h = Herramientas(tmp_path, sistema=False, memoria=memoria)

    h.ejecutar("recordar", {"hecho": "genero", "valor": "rock", "confirmado": False})
    salida, es_error = h.ejecutar(
        "recordar", {"hecho": "genero", "valor": "rock", "confirmado": True}
    )

    assert not es_error
    assert "pendiente" in salida.lower()
    assert memoria.guardados == []


def test_recordar_confirmado_en_turno_posterior_sin_mensaje_afirmativo_no_escribe(tmp_path):
    """El flag confirmado=true lo pone el MODELO, no el usuario: sin chequear
    lo que el usuario escribió de verdad, un mensaje inyectado podía hacer
    que el modelo se auto-confirmara sin que nadie dijera que sí."""
    memoria = _MemoriaFalsa()
    h = Herramientas(tmp_path, sistema=False, memoria=memoria)

    h.ejecutar("recordar", {"hecho": "genero", "valor": "rock", "confirmado": False})
    h.nuevo_turno("¿y mañana va a llover?")  # turno posterior, pero no es un sí
    salida, es_error = h.ejecutar(
        "recordar", {"hecho": "genero", "valor": "rock", "confirmado": True}
    )

    assert not es_error
    assert "pendiente" in salida.lower()
    assert memoria.guardados == []


def test_recordar_confirmado_en_turno_posterior_con_si_escribe(tmp_path):
    memoria = _MemoriaFalsa()
    h = Herramientas(tmp_path, sistema=False, memoria=memoria)

    h.ejecutar("recordar", {"hecho": "genero de musica preferido", "valor": "rock", "confirmado": False})
    h.nuevo_turno("sí, dale")
    salida, es_error = h.ejecutar(
        "recordar", {"hecho": "genero de musica preferido", "valor": "rock", "confirmado": True}
    )

    assert not es_error
    assert "rock" in salida
    assert memoria.guardados == [("genero de musica preferido", "rock")]


def test_recordar_si_en_turno_no_inmediato_no_escribe(tmp_path):
    """La confirmación tiene que atarse al pedido concreto: un pendiente
    viejo no debe quedar esperando cualquier "sí" futuro, de cualquier
    tema, turnos después."""
    memoria = _MemoriaFalsa()
    h = Herramientas(tmp_path, sistema=False, memoria=memoria)

    h.ejecutar("recordar", {"hecho": "genero", "valor": "rock", "confirmado": False})
    h.nuevo_turno("¿y mañana va a llover?")  # turno +1, no confirma nada
    h.nuevo_turno("sí")  # turno +2: afirmativo, pero ya no es el turno siguiente al pedido
    salida, es_error = h.ejecutar(
        "recordar", {"hecho": "genero", "valor": "rock", "confirmado": True}
    )

    assert not es_error
    assert "pendiente" in salida.lower()
    assert memoria.guardados == []


def test_recordar_negacion_que_contiene_palabra_afirmativa_no_escribe(tmp_path):
    """"no, dale, mejor cancelá" contiene "dale" (está en la lista de
    afirmaciones) pero el sentido real es un no — mirar solo la primera
    palabra evita este bypass."""
    memoria = _MemoriaFalsa()
    h = Herramientas(tmp_path, sistema=False, memoria=memoria)

    h.ejecutar("recordar", {"hecho": "genero", "valor": "rock", "confirmado": False})
    h.nuevo_turno("no, dale, mejor cancelá eso")
    salida, es_error = h.ejecutar(
        "recordar", {"hecho": "genero", "valor": "rock", "confirmado": True}
    )

    assert not es_error
    assert "pendiente" in salida.lower()
    assert memoria.guardados == []


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
