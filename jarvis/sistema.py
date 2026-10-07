"""Herramientas para manejar el equipo: carpetas, archivos y aplicaciones.

Pensadas para macOS (usan ``open`` y AppleScript). Por seguridad:

- Solo trabajan dentro de la carpeta personal del usuario.
- No hay ninguna herramienta para borrar ni mover archivos.
- Cerrar una aplicación exige que el usuario lo confirme en un mensaje
  posterior: la primera llamada solo deja la petición pendiente.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .herramientas import Herramientas

MAX_ELEMENTOS = 40
MAX_RESULTADOS = 20
MAX_CARPETAS_BUSQUEDA = 5000
MAX_TEXTO_PDF = 20000  # caracteres; de más, se trunca
# Carpetas enormes o internas que no merece la pena recorrer al buscar.
CARPETAS_IGNORADAS = {"Library", "node_modules", ".Trash", "__pycache__", ".git", ".venv"}
# Abrir estos archivos ejecutaría código, así que no se permite.
EXTENSIONES_EJECUTABLES = {".command", ".sh", ".tool", ".terminal", ".scpt", ".workflow"}

CARPETAS_EN_ESPANOL = {
    "escritorio": "Desktop", "documentos": "Documents", "descargas": "Downloads",
    "imágenes": "Pictures", "imagenes": "Pictures", "fotos": "Pictures", "música": "Music",
    "musica": "Music", "películas": "Movies", "peliculas": "Movies", "aplicaciones": "Applications",
}

Ejecutor = Callable[[list[str]], subprocess.CompletedProcess]


def _ejecutar(comando: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(comando, capture_output=True, text=True, timeout=20)


def registrar_sistema(h: "Herramientas", carpeta_personal: Path | None = None,
                      ejecutar: Ejecutor = _ejecutar) -> None:
    raiz = (carpeta_personal or Path.home()).resolve()

    def resolver(ruta: str) -> Path:
        """Convierte lo que diga el usuario en una ruta dentro de su carpeta personal."""
        ruta = ruta.strip() or "~"
        if ruta == "~" or ruta.startswith("~/"):
            ruta = ruta[2:]
        partes = Path(ruta).parts
        if partes and not (raiz / partes[0]).exists():
            # El Finder muestra "Documentos" pero en disco la carpeta es "Documents".
            primera = CARPETAS_EN_ESPANOL.get(partes[0].lower(), partes[0])
            ruta = str(Path(primera, *partes[1:]))
        destino = (raiz / ruta).resolve()
        if destino != raiz and raiz not in destino.parents:
            raise PermissionError("solo puedo acceder a carpetas dentro de tu carpeta personal")
        if not destino.exists():
            raise FileNotFoundError(f"no existe {_mostrar(destino)}")
        return destino

    def _mostrar(ruta: Path) -> str:
        return "~" if ruta == raiz else "~/" + str(ruta.relative_to(raiz))

    def comprobar(resultado: subprocess.CompletedProcess, que: str) -> None:
        if resultado.returncode != 0:
            detalle = (resultado.stderr or resultado.stdout or "").strip()
            raise RuntimeError(f"no he podido {que}" + (f": {detalle}" if detalle else ""))

    @h.registrar(
        "listar_carpeta",
        "Lista lo que hay dentro de una carpeta de la carpeta personal del usuario. "
        "La ruta es relativa a la carpeta personal (por ejemplo 'Documentos', 'Desktop', "
        "'Downloads/fotos'); usa '~' para la carpeta personal.",
        {"ruta": {"type": "string", "description": "Carpeta a listar, por ejemplo 'Documents'."}},
    )
    def listar_carpeta(ruta: str) -> str:
        carpeta = resolver(ruta)
        if not carpeta.is_dir():
            raise NotADirectoryError(f"{_mostrar(carpeta)} no es una carpeta")
        elementos = sorted(
            (e for e in carpeta.iterdir() if not e.name.startswith(".")),
            key=lambda e: (not e.is_dir(), e.name.lower()),
        )
        if not elementos:
            return f"{_mostrar(carpeta)} está vacía."
        lineas = [f"{e.name}/" if e.is_dir() else e.name for e in elementos[:MAX_ELEMENTOS]]
        if len(elementos) > MAX_ELEMENTOS:
            lineas.append(f"... y {len(elementos) - MAX_ELEMENTOS} más")
        return f"Contenido de {_mostrar(carpeta)} ({len(elementos)} elementos):\n" + "\n".join(lineas)

    @h.registrar(
        "buscar_archivos",
        "Busca archivos y carpetas cuyo nombre contenga un texto, dentro de una carpeta "
        "de la carpeta personal del usuario y sus subcarpetas.",
        {
            "texto": {"type": "string", "description": "Parte del nombre a buscar, por ejemplo 'factura'."},
            "carpeta": {"type": "string", "description": "Dónde buscar; '~' para toda la carpeta personal."},
        },
    )
    def buscar_archivos(texto: str, carpeta: str) -> str:
        inicio = resolver(carpeta)
        buscado = texto.strip().lower()
        if not buscado:
            raise ValueError("dime qué nombre buscar")
        encontrados: list[str] = []
        recorridas = 0
        for actual, subcarpetas, archivos in os.walk(inicio):
            recorridas += 1
            subcarpetas[:] = [s for s in subcarpetas
                              if not s.startswith(".") and s not in CARPETAS_IGNORADAS]
            for nombre in subcarpetas + archivos:
                if buscado in nombre.lower() and not nombre.startswith("."):
                    encontrados.append(_mostrar(Path(actual) / nombre))
                    if len(encontrados) >= MAX_RESULTADOS:
                        break
            if len(encontrados) >= MAX_RESULTADOS or recorridas >= MAX_CARPETAS_BUSQUEDA:
                break
        if not encontrados:
            return f"No he encontrado nada con '{texto}' en {_mostrar(inicio)}."
        return f"Encontrados {len(encontrados)}:\n" + "\n".join(encontrados)

    @h.registrar(
        "abrir_archivo_o_carpeta",
        "Abre un archivo con su aplicación habitual, o una carpeta en el Finder. "
        "La ruta es relativa a la carpeta personal del usuario.",
        {"ruta": {"type": "string", "description": "Por ejemplo 'Documents/informe.pdf' o 'Downloads'."}},
    )
    def abrir_archivo_o_carpeta(ruta: str) -> str:
        destino = resolver(ruta)
        if destino.is_file() and destino.suffix.lower() in EXTENSIONES_EJECUTABLES:
            raise PermissionError("por seguridad no abro scripts ejecutables")
        comprobar(ejecutar([_abridor(), str(destino)]), f"abrir {_mostrar(destino)}")
        return f"Abierto {_mostrar(destino)}."

    @h.registrar(
        "leer_pdf",
        "Extrae el texto de un PDF de la carpeta personal del usuario, para leerlo, "
        "resumirlo o responder preguntas sobre su contenido.",
        {"ruta": {"type": "string", "description": "Por ejemplo 'Documents/factura.pdf'."}},
    )
    def leer_pdf(ruta: str) -> str:
        destino = resolver(ruta)
        if destino.suffix.lower() != ".pdf":
            raise ValueError(f"{_mostrar(destino)} no es un PDF")
        from pypdf import PdfReader

        lector = PdfReader(destino)
        texto = "\n".join(pagina.extract_text() or "" for pagina in lector.pages).strip()
        if not texto:
            return f"{_mostrar(destino)} no tiene texto que se pueda extraer (¿quizás escaneado sin OCR?)."
        if len(texto) > MAX_TEXTO_PDF:
            texto = texto[:MAX_TEXTO_PDF] + "\n... (truncado)"
        return f"Contenido de {_mostrar(destino)} ({len(lector.pages)} páginas):\n{texto}"

    @h.registrar(
        "abrir_aplicacion",
        "Abre (o trae al frente) una aplicación del equipo por su nombre, por ejemplo "
        "'Safari', 'Spotify' o 'Visual Studio Code'. Si no la encuentra, prueba con su "
        "nombre en inglés (por ejemplo 'Notes' en lugar de 'Notas').",
        {"nombre": {"type": "string", "description": "Nombre de la aplicación."}},
    )
    def abrir_aplicacion(nombre: str) -> str:
        comprobar(ejecutar(["open", "-a", nombre.strip()]), f"abrir {nombre}")
        return f"{nombre} abierta."

    @h.registrar(
        "aplicaciones_abiertas",
        "Devuelve las aplicaciones que el usuario tiene abiertas ahora mismo.",
        {},
    )
    def aplicaciones_abiertas() -> str:
        resultado = ejecutar(["osascript", "-e",
                              'tell application "System Events" to get name of every '
                              "application process whose background only is false"])
        comprobar(resultado, "ver las aplicaciones abiertas")
        return "Aplicaciones abiertas: " + resultado.stdout.strip()

    @h.registrar(
        "cerrar_aplicacion",
        "Cierra una aplicación. Llámala primero con confirmado=false: eso deja el cierre "
        "pendiente. Entonces pregunta al usuario si de verdad quiere cerrarla (podría perder "
        "trabajo sin guardar) y espera su respuesta. Solo si en su siguiente mensaje dice que "
        "sí, vuelve a llamarla con confirmado=true.",
        {
            "nombre": {"type": "string", "description": "Nombre de la aplicación, por ejemplo 'Safari'."},
            "confirmado": {"type": "boolean",
                           "description": "true solo si el usuario ya ha confirmado el cierre."},
        },
    )
    def cerrar_aplicacion(nombre: str, confirmado: bool) -> str:
        clave = ("cerrar_aplicacion", nombre.strip().lower())
        if not h.autorizacion.pedir(clave, h.turno, confirmado, h.ultimo_mensaje_usuario):
            return (f"Cierre de {nombre} pendiente. Pregunta al usuario si quiere cerrarla y "
                    "espera a que responda antes de llamar con confirmado=true.")
        comprobar(ejecutar(["osascript", "-e", f'tell application "{_applescript(nombre)}" to quit']),
                  f"cerrar {nombre}")
        return f"{nombre} cerrada."


def _abridor() -> str:
    return "open" if sys.platform == "darwin" else "xdg-open"


def _applescript(texto: str) -> str:
    """Escapa un texto para meterlo entre comillas en AppleScript."""
    return texto.strip().replace("\\", "\\\\").replace('"', '\\"')
