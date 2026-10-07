"""Pruebas de las herramientas de carpetas y aplicaciones (sin tocar el equipo real)."""

import subprocess

import pytest

from jarvis.herramientas import Herramientas
from jarvis.sistema import registrar_sistema


class EjecutorFalso:
    def __init__(self, salida="", codigo=0):
        self.comandos = []
        self.salida, self.codigo = salida, codigo

    def __call__(self, comando):
        self.comandos.append(comando)
        return subprocess.CompletedProcess(comando, self.codigo, self.salida, "")


@pytest.fixture
def casa(tmp_path):
    casa = tmp_path / "casa"
    (casa / "Documents" / "trabajo").mkdir(parents=True)
    (casa / "Documents" / "factura_enero.pdf").write_text("x")
    (casa / "Documents" / "trabajo" / "factura_febrero.pdf").write_text("x")
    (casa / "Documents" / ".oculto").write_text("x")
    (casa / "Library" / "factura_cache").mkdir(parents=True)
    (casa / "script.command").write_text("rm -rf /")
    (tmp_path / "fuera.txt").write_text("secreto")
    return casa


@pytest.fixture
def sistema(tmp_path, casa):
    h = Herramientas(tmp_path / "datos", sistema=False)
    ejecutor = EjecutorFalso()
    registrar_sistema(h, carpeta_personal=casa, ejecutar=ejecutor)
    h.ejecutor = ejecutor
    return h


def test_listar_carpeta(sistema):
    salida, error = sistema.ejecutar("listar_carpeta", {"ruta": "Documents"})
    assert not error
    assert "trabajo/" in salida and "factura_enero.pdf" in salida and ".oculto" not in salida


def test_nombres_de_carpeta_en_espanol(sistema):
    salida, error = sistema.ejecutar("listar_carpeta", {"ruta": "Documentos/trabajo"})
    assert not error and "factura_febrero.pdf" in salida


def test_no_sale_de_la_carpeta_personal(sistema):
    for ruta in ("..", "~/../", "/etc", "../fuera.txt"):
        salida, error = sistema.ejecutar("listar_carpeta", {"ruta": ruta})
        assert error, ruta
    assert sistema.ejecutar("abrir_archivo_o_carpeta", {"ruta": "../fuera.txt"})[1]
    assert sistema.ejecutor.comandos == []


def test_buscar_archivos(sistema):
    salida, error = sistema.ejecutar("buscar_archivos", {"texto": "FACTURA", "carpeta": "~"})
    assert not error
    assert "~/Documents/factura_enero.pdf" in salida
    assert "~/Documents/trabajo/factura_febrero.pdf" in salida
    assert "Library" not in salida


def test_abrir_archivo(sistema, casa):
    salida, error = sistema.ejecutar("abrir_archivo_o_carpeta", {"ruta": "Documents/factura_enero.pdf"})
    assert not error
    assert sistema.ejecutor.comandos[-1][-1] == str((casa / "Documents" / "factura_enero.pdf").resolve())


def test_no_abre_scripts(sistema):
    assert sistema.ejecutar("abrir_archivo_o_carpeta", {"ruta": "script.command"})[1]
    assert sistema.ejecutor.comandos == []


def test_abrir_aplicacion(sistema):
    assert not sistema.ejecutar("abrir_aplicacion", {"nombre": "Safari"})[1]
    assert sistema.ejecutor.comandos == [["open", "-a", "Safari"]]


def test_cerrar_aplicacion_exige_confirmacion_en_otro_mensaje(sistema):
    sistema.nuevo_turno()
    # Aunque diga confirmado=true, sin haber preguntado antes no cierra nada.
    salida, _ = sistema.ejecutar("cerrar_aplicacion", {"nombre": "Safari", "confirmado": True})
    assert "pendiente" in salida
    # Tampoco vale confirmar en el mismo mensaje en que se pidió.
    sistema.ejecutar("cerrar_aplicacion", {"nombre": "Safari", "confirmado": True})
    assert sistema.ejecutor.comandos == []


    sistema.nuevo_turno("sí")  # el usuario responde "sí"
    salida, error = sistema.ejecutar("cerrar_aplicacion", {"nombre": "safari", "confirmado": True})
    assert not error and "cerrada" in salida
    assert sistema.ejecutor.comandos == [["osascript", "-e", 'tell application "safari" to quit']]


def test_cerrar_aplicacion_no_confirma_sin_un_si_real(sistema):
    """Antes de generalizar la autorización (ver jarvis.autorizacion), esta
    herramienta no exigía que el mensaje del usuario sonara afirmativo: un
    confirmado=true alcanzaba, viniera de donde viniera. Mismo caso que
    protege "recordar" contra una instrucción inyectada."""
    sistema.ejecutar("cerrar_aplicacion", {"nombre": "Safari", "confirmado": False})
    sistema.nuevo_turno("¿y qué hora es?")  # turno siguiente, pero no es un sí
    salida, _ = sistema.ejecutar("cerrar_aplicacion", {"nombre": "Safari", "confirmado": True})
    assert "pendiente" in salida
    assert sistema.ejecutor.comandos == []


def _pdf_minimo(texto: str) -> bytes:
    """Arma a mano un PDF válido de una página con el texto dado (sin dependencias)."""
    objetos = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>"
        b"/MediaBox[0 0 200 200]/Contents 5 0 R>>endobj\n",
        b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
        f"5 0 obj<</Length {len(texto) + 25}>>\nstream\nBT /F1 24 Tf 20 100 Td ({texto}) Tj ET\n"
        "endstream\nendobj\n".encode(),
    ]
    cuerpo = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objetos:
        offsets.append(len(cuerpo))
        cuerpo += obj
    xref = b"xref\n0 6\n0000000000 65535 f \n" + b"".join(
        f"{off:010d} 00000 n \n".encode() for off in offsets[1:]
    )
    trailer = f"trailer<</Size 6/Root 1 0 R>>\nstartxref\n{len(cuerpo)}\n%%EOF".encode()
    return cuerpo + xref + trailer


def test_leer_pdf_extrae_texto(sistema, casa):
    (casa / "Documents" / "informe.pdf").write_bytes(_pdf_minimo("Hola PDF"))
    salida, error = sistema.ejecutar("leer_pdf", {"ruta": "Documents/informe.pdf"})
    assert not error
    assert "Hola PDF" in salida


def test_leer_pdf_rechaza_archivos_que_no_son_pdf(sistema):
    salida, error = sistema.ejecutar("leer_pdf", {"ruta": "script.command"})
    assert error
    assert "no es un PDF" in salida


def test_leer_pdf_trunca_texto_largo(sistema, casa, monkeypatch):
    import jarvis.sistema as sistema_mod

    monkeypatch.setattr(sistema_mod, "MAX_TEXTO_PDF", 5)
    (casa / "Documents" / "largo.pdf").write_bytes(_pdf_minimo("Hola PDF"))
    salida, error = sistema.ejecutar("leer_pdf", {"ruta": "Documents/largo.pdf"})
    assert not error
    assert "(truncado)" in salida


def test_cerrar_aplicacion_escapa_comillas(sistema):
    sistema.ejecutar("cerrar_aplicacion", {"nombre": 'X" to quit\ndo shell script "ls', "confirmado": False})
    sistema.nuevo_turno("sí")
    sistema.ejecutar("cerrar_aplicacion", {"nombre": 'X" to quit\ndo shell script "ls', "confirmado": True})
    script = sistema.ejecutor.comandos[-1][-1]
    assert script.startswith('tell application "X\\" to quit')


def test_no_hay_herramientas_de_borrar(tmp_path):
    nombres = {d["name"] for d in Herramientas(tmp_path).definiciones()}
    assert {"listar_carpeta", "abrir_aplicacion", "cerrar_aplicacion"} <= nombres
    assert not any(p in n for n in nombres for p in ("borrar", "eliminar", "mover"))
