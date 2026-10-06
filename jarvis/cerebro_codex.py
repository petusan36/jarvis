"""Cerebro alternativo que usa tu sesión de Codex CLI (OpenAI) en lugar de
una clave de API.

Funciona invocando ``codex exec`` — el modo no interactivo de Codex CLI,
pensado para automatización/CI — en un subproceso. La sesión la maneja el
propio Codex CLI (normalmente en ``~/.codex/auth.json``, o el keychain del
sistema operativo si configuraste ``storage=keyring``): Jarvis no la lee,
no la pide y no la guarda, igual que ``cerebro_suscripcion.py`` con Claude
Code.

Dos cosas verificadas de verdad en una instalación real (codex-cli
0.160.1), porque el texto de ``codex exec`` sin ``--json`` no es seguro de
parsear (trae un banner con workdir/model/session id/tokens, con colores
ANSI, antes de la respuesta):

- ``--json`` imprime eventos JSONL limpios por stdout; el primero,
  ``{"type":"thread.started","thread_id":"<uuid>"}``, da el id de sesión.
- ``-o/--output-last-message <archivo>`` escribe SOLO la respuesta final
  del agente a un archivo — es lo que hay que leer, nunca ``stdout``.
- El primer turno de una conversación es ``codex exec ... <prompt>``; los
  siguientes son ``codex exec resume <thread_id> ... <mensaje>``, que
  continúa la misma sesión sin que Jarvis tenga que reenviar el historial
  como texto. ``resume`` no acepta ``--sandbox`` (la sesión ya resumida
  usa la configuración con la que arrancó).

Limitación conocida (TODO): a diferencia de ``cerebro_suscripcion.py``, no
le pasamos las herramientas de Jarvis a Codex como servidor MCP. Codex CLI
soporta MCP, pero conectarlo así queda pendiente — por ahora cada turno es
solo conversación de texto.

Pensado solo para uso personal en tu propio equipo: no lo compartas con
otras personas usando tu cuenta.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .cerebro import INSTRUCCIONES
from .config import Config
from .herramientas import Herramientas

TIMEOUT_SEGUNDOS = 120

Ejecutor = Callable[[list[str]], subprocess.CompletedProcess]


def _ejecutar(comando: list[str]) -> subprocess.CompletedProcess:
    # stdin=DEVNULL: sin esto, "codex exec" intenta leer stdin adicional y
    # podría quedarse esperando si el proceso que lanza Jarvis no tiene un
    # stdin ya cerrado (p. ej. corriendo como app de escritorio).
    return subprocess.run(
        comando, capture_output=True, text=True, timeout=TIMEOUT_SEGUNDOS, stdin=subprocess.DEVNULL,
    )


class CerebroCodex:
    def __init__(self, config: Config, herramientas: Herramientas, ejecutar: Ejecutor = _ejecutar):
        if shutil.which("codex") is None:
            raise RuntimeError(
                "Falta Codex CLI. Instálalo con: npm install -g @openai/codex\n"
                "Después, ejecuta `codex login` e inicia sesión con tu cuenta."
            )
        self.config = config
        self.herramientas = herramientas
        self._ejecutar = ejecutar
        # id de la sesión de Codex en curso; None = todavía no hay ninguna
        # (el próximo turno arranca una nueva, con las instrucciones de Jarvis).
        self._id_sesion: str | None = None

    def responder(self, texto_usuario: str) -> str:
        self.herramientas.nuevo_turno()

        descriptor = tempfile.NamedTemporaryFile(prefix="jarvis-codex-", suffix=".txt", delete=False)
        ruta_salida = Path(descriptor.name)
        descriptor.close()
        try:
            comando = self._construir_comando(texto_usuario, ruta_salida)
            try:
                resultado = self._ejecutar(comando)
            except FileNotFoundError:
                return "Falta Codex CLI. Instálalo con: npm install -g @openai/codex"
            except subprocess.TimeoutExpired:
                return "Codex está tardando demasiado en responder. Probá de nuevo."

            if resultado.returncode != 0:
                return _mensaje_de_error(resultado.stderr)

            id_sesion = _extraer_id_sesion(resultado.stdout)
            if id_sesion:
                self._id_sesion = id_sesion

            texto = ruta_salida.read_text("utf-8").strip() if ruta_salida.is_file() else ""
            return texto or "..."
        finally:
            ruta_salida.unlink(missing_ok=True)

    def _construir_comando(self, texto_usuario: str, ruta_salida: Path) -> list[str]:
        if self._id_sesion is None:
            # Primer turno: arranca una sesión nueva con las instrucciones de Jarvis.
            prompt = f"{INSTRUCCIONES.format(nombre=self.config.nombre_usuario)}\n\n{texto_usuario}"
            return [
                "codex", "exec",
                "--skip-git-repo-check", "--sandbox", "read-only", "--json",
                "-o", str(ruta_salida),
                prompt,
            ]
        # Turnos siguientes: continúa la misma sesión, sin reenviar nada más.
        return [
            "codex", "exec", "resume", self._id_sesion,
            "--skip-git-repo-check", "--json",
            "-o", str(ruta_salida),
            texto_usuario,
        ]

    def olvidar(self) -> None:
        """Empieza una conversación nueva: el próximo turno abre otra sesión."""
        self._id_sesion = None


def _extraer_id_sesion(salida_jsonl: str) -> str | None:
    """Busca el evento ``thread.started`` en la salida ``--json`` (JSONL) y
    devuelve su ``thread_id``, que es el id que acepta ``codex exec resume``."""
    for linea in salida_jsonl.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            evento = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if evento.get("type") == "thread.started":
            return evento.get("thread_id")
    return None


def _mensaje_de_error(stderr: str | None) -> str:
    stderr = (stderr or "").strip()
    minuscula = stderr.lower()
    if "login" in minuscula or "auth" in minuscula or "unauthorized" in minuscula:
        return "Todavía no iniciaste sesión en Codex. Ejecuta `codex login` y volvé a intentar."
    return f"Algo falló al consultar a Codex{f': {stderr}' if stderr else '.'}"
