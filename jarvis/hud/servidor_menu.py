"""Servidor HTTP local para el menú de conexión con IA cuando no hay una
terminal interactiva disponible (ej. arrancado desde el ícono de escritorio).

Sigue el mismo patrón que ``hud.Hud``: un ``ThreadingHTTPServer`` liviano,
solo con la biblioteca estándar, sirviendo una página (``menu.html``) que
hace polling de ``GET /estado`` y manda las elecciones del usuario por
``POST /accion``. A diferencia del HUD (que solo empuja estado hacia la
página), acá también hay que recibir clics: por eso ``ServidorMenu`` expone
una cola de acciones que el hilo de trabajo de Python puede esperar con
``esperar_accion``.

El estado es intencionalmente un diccionario libre (no un enum cerrado):
quien orquesta el flujo (ver ``jarvis.__main__._atender_menu_ventana`` y
funciones relacionadas) decide qué claves manda en cada paso; esta clase
solo lo guarda y lo sirve.
"""

from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any


class ServidorMenu:
    """Levanta el servidor y lo deja escuchando en un hilo aparte."""

    def __init__(self, puerto: int = 0):
        self._cerrojo = threading.Lock()
        self._estado: dict[str, Any] = {"paso": "inicio"}
        self._acciones: queue.Queue = queue.Queue()
        self._servidor = _crear_servidor(puerto, self)
        self.url = f"http://127.0.0.1:{self._servidor.server_address[1]}/"
        threading.Thread(target=self._servidor.serve_forever, daemon=True).start()

    def estado(self) -> dict:
        """Copia del estado actual (lo que ve/vería la página al pollear)."""
        with self._cerrojo:
            return dict(self._estado)

    def actualizar(self, **cambios: Any) -> None:
        """Reemplaza por completo el estado visible, salvo las claves no
        incluidas en ``cambios`` que se pisan con valores por defecto: cada
        paso del menú manda su estado completo, no un parche, para que la
        página nunca muestre datos de un paso anterior por error."""
        with self._cerrojo:
            self._estado = dict(cambios)

    def esperar_accion(self, timeout: float | None = None) -> dict | None:
        """Bloquea (en el hilo de trabajo, no en el de la UI) hasta que
        llegue una acción del usuario o se agote ``timeout``. Devuelve
        ``None`` si se agotó el tiempo."""
        try:
            return self._acciones.get(timeout=timeout)
        except queue.Empty:
            return None

    def _recibir_accion(self, accion: dict) -> None:
        self._acciones.put(accion)

    def cerrar(self) -> None:
        self._servidor.shutdown()
        self._servidor.server_close()


def _crear_servidor(puerto: int, servidor_menu: ServidorMenu) -> ThreadingHTTPServer:
    pagina = resources.files(__package__).joinpath("menu.html").read_bytes()

    class Manejador(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                self._enviar(200, "text/html; charset=utf-8", pagina)
            elif self.path == "/estado":
                cuerpo = json.dumps(servidor_menu.estado(), ensure_ascii=False).encode()
                self._enviar(200, "application/json; charset=utf-8", cuerpo)
            else:
                self._enviar(404, "text/plain; charset=utf-8", b"No encontrado")

        def do_POST(self):
            if self.path != "/accion":
                self._enviar(404, "text/plain; charset=utf-8", b"No encontrado")
                return
            largo = int(self.headers.get("Content-Length", 0))
            crudo = self.rfile.read(largo) if largo else b"{}"
            try:
                accion = json.loads(crudo.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                accion = {}
            servidor_menu._recibir_accion(accion)
            self._enviar(204, "text/plain; charset=utf-8", b"")

        def _enviar(self, codigo: int, tipo: str, cuerpo: bytes) -> None:
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *_args) -> None:
            pass  # sin ruido en el log de Jarvis

    class _Servidor(ThreadingHTTPServer):
        daemon_threads = True

    try:
        return _Servidor(("127.0.0.1", puerto), Manejador)
    except OSError:
        return _Servidor(("127.0.0.1", 0), Manejador)  # puerto ocupado: usa otro libre
