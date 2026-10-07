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
quien orquesta el flujo (ver ``jarvis.conexion_ia._atender_menu_ventana`` y
funciones relacionadas) decide qué claves manda en cada paso; esta clase
solo lo guarda y lo sirve.
"""

from __future__ import annotations

import json
import queue
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any

_LARGO_MAXIMO_ACCION = 4096  # el cuerpo de /accion es un click, no debería pesar nada


class ServidorMenu:
    """Levanta el servidor y lo deja escuchando en un hilo aparte.

    ``POST /accion`` dispara pasos con efectos reales (elegir modelo, abrir
    una Terminal y correr ``codex login``/``claude``), así que no puede
    quedar abierto sin autenticar: cualquier página que el usuario tenga
    abierta en su navegador mientras este servidor está vivo podría
    mandarle un POST (es un ``fetch`` simple, sin preflight de CORS, igual
    que el que usa ``menu.html``). Por eso cada instancia genera un token
    al azar, lo embebe en la página que sirve (que una página de otro
    origen no puede leer) y exige ese mismo token en cada ``POST /accion``
    vía el encabezado ``X-Jarvis-Token``."""

    def __init__(self, puerto: int = 0):
        self.token = secrets.token_urlsafe(32)
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
    plantilla = resources.files(__package__).joinpath("menu.html").read_text(encoding="utf-8")
    pagina = plantilla.replace("__JARVIS_TOKEN__", servidor_menu.token).encode("utf-8")

    class Manejador(BaseHTTPRequestHandler):
        def _host_valido(self) -> bool:
            """Defensa contra DNS rebinding: un dominio controlado por un
            atacante puede apuntar a 127.0.0.1 después de que el navegador
            ya lo trató como "mismo origen" que su propio JS, lo que deja
            leer el token embebido en la página (burlando esa protección)
            en vez de solo adivinarlo. El encabezado Host que manda el
            navegador sigue siendo el del dominio del atacante, no
            127.0.0.1 — por eso alcanza con exigir que coincida."""
            return self.headers.get("Host", "") == f"127.0.0.1:{self.server.server_address[1]}"

        def do_GET(self):
            if not self._host_valido():
                self._enviar(403, "text/plain; charset=utf-8", b"Host invalido")
                return
            if self.path == "/":
                self._enviar(200, "text/html; charset=utf-8", pagina)
            elif self.path == "/estado":
                cuerpo = json.dumps(servidor_menu.estado(), ensure_ascii=False).encode()
                self._enviar(200, "application/json; charset=utf-8", cuerpo)
            else:
                self._enviar(404, "text/plain; charset=utf-8", b"No encontrado")

        def do_POST(self):
            if not self._host_valido():
                self._enviar(403, "text/plain; charset=utf-8", b"Host invalido")
                return
            if self.path != "/accion":
                self._enviar(404, "text/plain; charset=utf-8", b"No encontrado")
                return
            if not secrets.compare_digest(self.headers.get("X-Jarvis-Token", ""), servidor_menu.token):
                self._enviar(403, "text/plain; charset=utf-8", b"Token invalido")
                return
            largo = int(self.headers.get("Content-Length", 0))
            if largo > _LARGO_MAXIMO_ACCION:
                self._enviar(413, "text/plain; charset=utf-8", b"Cuerpo demasiado grande")
                return
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
