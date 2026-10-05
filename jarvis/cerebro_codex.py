"""Cerebro alternativo que usa tu sesión de Codex CLI (OpenAI) en lugar de
una clave de API.

Funciona invocando ``codex exec`` — el modo no interactivo de Codex CLI,
pensado para automatización/CI — en un subproceso. La sesión la maneja el
propio Codex CLI (normalmente en ``~/.codex/auth.json``, o el keychain del
sistema operativo si configuraste ``storage=keyring``): Jarvis no la lee,
no la pide y no la guarda, igual que ``cerebro_suscripcion.py`` con Claude
Code.

Limitaciones conocidas (TODO):

- No le pasamos las herramientas de Jarvis a Codex como servidor MCP
  (``cerebro_suscripcion.py`` sí lo hace para Claude, vía
  ``create_sdk_mcp_server``). Codex CLI soporta MCP, pero conectarlo así
  queda pendiente — por ahora cada turno es solo conversación de texto.
- ``codex exec`` no mantiene la sesión entre invocaciones de forma que
  pudiéramos verificar en esta máquina (el binario instalado estaba roto:
  ``codex`` no ejecutaba nada, ver nota en el README/commit). Mientras no
  se confirme el mecanismo real de continuar una sesión, cada turno manda
  la conversación completa como texto plano (igual que ``Cerebro`` reenvía
  todo su historial en cada llamada a la API).
- Los nombres de flags (``--skip-git-repo-check``, ``--sandbox
  read-only``) vienen de la documentación pública de Codex CLI, no de
  ``codex exec --help`` corrido en esta máquina (la instalación local
  estaba rota). Si tu versión de Codex los nombra distinto, ajustalos acá.

Pensado solo para uso personal en tu propio equipo: no lo compartas con
otras personas usando tu cuenta.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Callable

from .cerebro import INSTRUCCIONES
from .config import Config
from .herramientas import Herramientas

TIMEOUT_SEGUNDOS = 120

Ejecutor = Callable[[list[str]], subprocess.CompletedProcess]


def _ejecutar(comando: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(comando, capture_output=True, text=True, timeout=TIMEOUT_SEGUNDOS)


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
        # (rol, texto); se reenvía completo en cada turno, ver limitaciones arriba.
        self.historial: list[tuple[str, str]] = []

    def responder(self, texto_usuario: str) -> str:
        self.herramientas.nuevo_turno()
        self.historial.append(("usuario", texto_usuario))
        prompt = _construir_prompt(self.config, self.historial)

        try:
            resultado = self._ejecutar([
                "codex", "exec",
                "--skip-git-repo-check",
                "--sandbox", "read-only",
                prompt,
            ])
        except FileNotFoundError:
            return "Falta Codex CLI. Instálalo con: npm install -g @openai/codex"
        except subprocess.TimeoutExpired:
            return "Codex está tardando demasiado en responder. Probá de nuevo."

        if resultado.returncode != 0:
            return _mensaje_de_error(resultado.stderr)

        texto = resultado.stdout.strip()
        self.historial.append(("asistente", texto))
        return texto or "..."

    def olvidar(self) -> None:
        """Empieza una conversación nueva."""
        self.historial.clear()


def _construir_prompt(config: Config, historial: list[tuple[str, str]]) -> str:
    """Codex CLI no nos dio (en esta máquina) una forma verificada de pasar
    un system prompt separado ni de continuar una sesión entre llamadas, así
    que se manda todo como un único texto: instrucciones + transcripción."""
    partes = [INSTRUCCIONES.format(nombre=config.nombre_usuario)]
    for rol, texto in historial:
        partes.append(f"{'Usuario' if rol == 'usuario' else 'Jarvis'}: {texto}")
    return "\n\n".join(partes)


def _mensaje_de_error(stderr: str | None) -> str:
    stderr = (stderr or "").strip()
    minuscula = stderr.lower()
    if "login" in minuscula or "auth" in minuscula or "unauthorized" in minuscula:
        return "Todavía no iniciaste sesión en Codex. Ejecuta `codex login` y volvé a intentar."
    return f"Algo falló al consultar a Codex{f': {stderr}' if stderr else '.'}"
