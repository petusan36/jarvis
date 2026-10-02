"""HUD estilo Jarvis: anillos animados en el navegador que reaccionan al estado.

Solo usa la biblioteca estándar: un pequeño servidor HTTP local sirve la página
(hud.html, un canvas) y le envía los cambios de estado por Server-Sent Events.
"""

from __future__ import annotations

import json
import queue
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

ESTADOS = {"reposo", "escuchando", "pensando", "hablando"}


class HudNulo:
    """Sustituto que no hace nada, para cuando el HUD está desactivado."""

    def estado(self, nombre: str, texto: str | None = None) -> None:
        pass

    def nivel(self, valor: float) -> None:
        pass

    def cerrar(self) -> None:
        pass


class Hud(HudNulo):
    """Servidor local del HUD. Abre http://127.0.0.1:<puerto> en el navegador."""

    def __init__(self, puerto: int = 8765, abrir_navegador: bool = True):
        self._clientes: list[queue.Queue] = []
        self._cerrojo = threading.Lock()
        self._ultimo = {"tipo": "estado", "estado": "reposo", "texto": ""}
        self._servidor = _crear_servidor(puerto, self)
        self.url = f"http://127.0.0.1:{self._servidor.server_address[1]}/"
        threading.Thread(target=self._servidor.serve_forever, daemon=True).start()
        if abrir_navegador:
            webbrowser.open(self.url)

    def estado(self, nombre: str, texto: str | None = None) -> None:
        """Cambia la animación (reposo, escuchando, pensando o hablando) y, si se da, el texto."""
        if nombre not in ESTADOS:
            raise ValueError(f"Estado desconocido: {nombre}")
        if texto is None:
            texto = self._ultimo["texto"]
        self._ultimo = {"tipo": "estado", "estado": nombre, "texto": texto}
        self._emitir(self._ultimo)

    def nivel(self, valor: float) -> None:
        """Volumen del micrófono entre 0 y 1, para que los anillos vibren con la voz."""
        self._emitir({"tipo": "nivel", "valor": round(max(0.0, min(1.0, valor)), 3)})

    def cerrar(self) -> None:
        self._emitir(None)
        self._servidor.shutdown()
        self._servidor.server_close()

    def _suscribir(self) -> queue.Queue:
        cola: queue.Queue = queue.Queue()
        cola.put(self._ultimo)
        with self._cerrojo:
            self._clientes.append(cola)
        return cola

    def _desuscribir(self, cola: queue.Queue) -> None:
        with self._cerrojo:
            if cola in self._clientes:
                self._clientes.remove(cola)

    def _emitir(self, evento: dict | None) -> None:
        with self._cerrojo:
            for cola in self._clientes:
                cola.put(evento)


def _crear_servidor(puerto: int, hud: Hud) -> ThreadingHTTPServer:
    pagina = resources.files(__package__).joinpath("hud.html").read_bytes()

    class Manejador(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                self._enviar(200, "text/html; charset=utf-8", pagina)
            elif self.path == "/eventos":
                self._eventos()
            else:
                self._enviar(404, "text/plain; charset=utf-8", b"No encontrado")

        def _enviar(self, codigo: int, tipo: str, cuerpo: bytes) -> None:
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def _eventos(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            cola = hud._suscribir()
            try:
                while True:
                    try:
                        evento = cola.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": sigo aqui\n\n")  # mantiene viva la conexión
                    else:
                        if evento is None:
                            return
                        datos = json.dumps(evento, ensure_ascii=False)
                        self.wfile.write(f"data: {datos}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                hud._desuscribir(cola)

        def log_message(self, *_args) -> None:
            pass  # sin ruido en la consola de Jarvis

    try:
        return _Servidor(("127.0.0.1", puerto), Manejador)
    except OSError:
        return _Servidor(("127.0.0.1", 0), Manejador)  # puerto ocupado: usa otro libre


class _Servidor(ThreadingHTTPServer):
    daemon_threads = True  # las conexiones abiertas no impiden salir de Jarvis
