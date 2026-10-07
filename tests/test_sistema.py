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


class EjecutorShellFalso:
    def __init__(self, stdout="ok", stderr="", codigo=0):
        self.llamadas = []
        self.stdout, self.stderr, self.codigo = stdout, stderr, codigo

    def __call__(self, comando, carpeta):
        self.llamadas.append((comando, carpeta))
        return subprocess.CompletedProcess(comando, self.codigo, self.stdout, self.stderr)


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
    ejecutor_shell = EjecutorShellFalso()
    registrar_sistema(h, carpeta_personal=casa, ejecutar=ejecutor, ejecutar_shell=ejecutor_shell)
    h.ejecutor = ejecutor
    h.ejecutor_shell = ejecutor_shell
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
    """Ninguna herramienta se LLAMA "borrar"/"eliminar"/"mover" — pero
    ejecutar_comando sí puede hacer eso (es la excepción deliberada: corre
    cualquier shell, con su propia confirmación en dos pasos). Esta prueba
    documenta el nombrado, no una garantía de que nada borra nada."""
    nombres = {d["name"] for d in Herramientas(tmp_path).definiciones()}
    assert {"listar_carpeta", "abrir_aplicacion", "cerrar_aplicacion", "ejecutar_comando"} <= nombres
    assert not any(p in n for n in nombres for p in ("borrar", "eliminar", "mover"))


# --- escribir_archivo ------------------------------------------------------

def _escribir_confirmado(sistema, ruta, contenido):
    """escribir_archivo exige el mismo gate en dos pasos que recordar/
    crear_habilidad/ejecutar_comando (ver hallazgo de seguridad real)."""
    sistema.nuevo_turno("escribí ese archivo")
    sistema.ejecutar("escribir_archivo", {"ruta": ruta, "contenido": contenido, "confirmado": False})
    sistema.nuevo_turno("sí, dale")
    return sistema.ejecutar("escribir_archivo", {"ruta": ruta, "contenido": contenido, "confirmado": True})


def test_escribir_archivo_sin_confirmar_queda_pendiente_y_no_escribe(sistema, casa):
    salida, error = sistema.ejecutar("escribir_archivo", {
        "ruta": "Documents/trabajo/main.py", "contenido": "print('hola')", "confirmado": False,
    })
    assert not error
    assert "pendiente" in salida.lower()
    assert not (casa / "Documents" / "trabajo" / "main.py").is_file()


def test_escribir_archivo_confirmar_no_permite_cambiar_el_contenido(sistema, casa):
    """Mismo hallazgo de seguridad que crear_habilidad/ejecutar_comando: la
    confirmación se ata a la ruta Y un hash del contenido — si cambia el
    contenido entre el pedido y la confirmación, cuenta como un pedido
    nuevo, no uno ya aprobado."""
    sistema.ejecutar("escribir_archivo", {
        "ruta": "Documents/trabajo/main.py", "contenido": "contenido inocente", "confirmado": False,
    })
    sistema.nuevo_turno("sí, dale")
    salida, error = sistema.ejecutar("escribir_archivo", {
        "ruta": "Documents/trabajo/main.py", "contenido": "contenido CAMBIADO", "confirmado": True,
    })
    assert not error
    assert "pendiente" in salida.lower()
    assert not (casa / "Documents" / "trabajo" / "main.py").is_file()


def test_escribir_archivo_confirmado_crea_el_archivo(sistema, casa):
    salida, error = _escribir_confirmado(sistema, "Documents/trabajo/main.py", "print('hola')")
    assert not error
    assert (casa / "Documents" / "trabajo" / "main.py").read_text() == "print('hola')"
    assert "main.py" in salida


def test_escribir_archivo_sin_carpeta_destino_falla(sistema):
    salida, error = _escribir_confirmado(sistema, "Documents/no-existe/main.py", "x")
    assert error


def test_escribir_archivo_no_escapa_la_carpeta_personal(sistema):
    salida, error = _escribir_confirmado(sistema, "../fuera.txt", "malicioso")
    assert error


def test_escribir_archivo_reemplaza_uno_existente(sistema, casa):
    _escribir_confirmado(sistema, "Documents/trabajo/x.txt", "viejo")
    _escribir_confirmado(sistema, "Documents/trabajo/x.txt", "nuevo")
    assert (casa / "Documents" / "trabajo" / "x.txt").read_text() == "nuevo"


def test_escribir_archivo_requiere_dueño(sistema, casa):
    sistema.nuevo_turno("escribí esto", es_dueño=False)
    salida, error = sistema.ejecutar("escribir_archivo", {
        "ruta": "Documents/trabajo/x.txt", "contenido": "x", "confirmado": False,
    })
    assert not error
    assert "no puedo ejecutar" in salida.lower()


def test_escribir_archivo_rechaza_dotfiles(sistema):
    """Un dotfile (.ssh/authorized_keys, .zshrc, ...) equivale a ejecutar
    código — hallazgo de seguridad real: antes no había ningún bloqueo."""
    salida, error = _escribir_confirmado(sistema, ".zshrc", "echo hackeado")
    assert error


def test_escribir_archivo_rechaza_dot_carpetas(sistema):
    salida, error = _escribir_confirmado(sistema, ".ssh/authorized_keys", "ssh-ed25519 AAAA...")
    assert error


def test_escribir_archivo_rechaza_library(sistema):
    """Library/LaunchAgents/*.plist se ejecuta solo al iniciar sesión en macOS."""
    salida, error = _escribir_confirmado(sistema, "Library/LaunchAgents/evil.plist", "<xml/>")
    assert error


def test_escribir_archivo_rechaza_library_sin_importar_mayusculas(sistema):
    """Hallazgo real: APFS/HFS+ (el filesystem por defecto de macOS) es
    insensible a mayúsculas — "library" y "Library" son la misma carpeta
    en disco, aunque "library" == "Library" sea False en Python. El primer
    intento de este fix comparaba sin casefold y quedaba bypasseable con
    cualquier variación de mayúsculas."""
    salida, error = _escribir_confirmado(sistema, "library/LaunchAgents/evil.plist", "<xml/>")
    assert error
    salida, error = _escribir_confirmado(sistema, "LIBRARY/LaunchAgents/evil.plist", "<xml/>")
    assert error


# --- abrir_aplicacion con ruta ----------------------------------------------

def test_abrir_aplicacion_sin_ruta_igual_que_antes(sistema):
    sistema.ejecutar("abrir_aplicacion", {"nombre": "Safari", "ruta": ""})
    assert sistema.ejecutor.comandos == [["open", "-a", "Safari"]]


def test_abrir_aplicacion_con_ruta_la_pasa_al_comando(sistema, casa):
    sistema.ejecutar("abrir_aplicacion", {"nombre": "Visual Studio Code", "ruta": "Documents/trabajo"})
    comando = sistema.ejecutor.comandos[-1]
    assert comando[:3] == ["open", "-a", "Visual Studio Code"]
    assert comando[3] == str(casa / "Documents" / "trabajo")


def test_abrir_aplicacion_con_ruta_fuera_de_la_carpeta_personal_falla(sistema):
    salida, error = sistema.ejecutar("abrir_aplicacion", {"nombre": "Safari", "ruta": "../fuera.txt"})
    assert error


# --- ejecutar_comando -------------------------------------------------------

def test_ejecutar_comando_sin_confirmar_queda_pendiente_y_no_corre_nada(sistema):
    salida, error = sistema.ejecutar("ejecutar_comando", {"comando": "echo hola", "confirmado": False})
    assert not error
    assert "pendiente" in salida.lower()
    assert sistema.ejecutor_shell.llamadas == []


def test_ejecutar_comando_confirmado_en_el_mismo_turno_no_corre(sistema):
    sistema.ejecutar("ejecutar_comando", {"comando": "echo hola", "confirmado": False})
    sistema.ejecutar("ejecutar_comando", {"comando": "echo hola", "confirmado": True})
    assert sistema.ejecutor_shell.llamadas == []


def test_ejecutar_comando_confirmar_no_permite_cambiar_el_comando(sistema):
    """Mismo hallazgo de seguridad que crear_habilidad: la confirmación se
    ata al comando exacto, no solo a que "algo" se confirmó — si cambia el
    comando entre el pedido y la confirmación, cuenta como un pedido nuevo."""
    sistema.ejecutar("ejecutar_comando", {"comando": "echo inocente", "confirmado": False})
    sistema.nuevo_turno("sí, dale")
    salida, error = sistema.ejecutar("ejecutar_comando", {"comando": "rm -rf /", "confirmado": True})
    assert not error
    assert "pendiente" in salida.lower()
    assert sistema.ejecutor_shell.llamadas == []


def test_ejecutar_comando_confirmado_en_turno_siguiente_corre_y_devuelve_salida(sistema, casa):
    sistema.ejecutor_shell.stdout = "listo"
    sistema.ejecutar("ejecutar_comando", {"comando": "echo hola", "confirmado": False})
    sistema.nuevo_turno("sí, dale")

    salida, error = sistema.ejecutar("ejecutar_comando", {"comando": "echo hola", "confirmado": True})

    assert not error
    assert "listo" in salida
    assert sistema.ejecutor_shell.llamadas == [("echo hola", casa)]


def test_ejecutar_comando_requiere_dueño(sistema):
    sistema.nuevo_turno("corré esto", es_dueño=False)
    salida, error = sistema.ejecutar("ejecutar_comando", {"comando": "echo hola", "confirmado": False})
    assert not error
    assert "no puedo ejecutar" in salida.lower()
    assert sistema.ejecutor_shell.llamadas == []


def test_ejecutar_comando_vacio_falla(sistema):
    assert sistema.ejecutar("ejecutar_comando", {"comando": "   ", "confirmado": False})[1] is True
