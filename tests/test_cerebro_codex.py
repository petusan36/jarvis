"""Pruebas de CerebroCodex: todas con un ejecutor falso, sin invocar el
binario real de Codex CLI."""

from __future__ import annotations

import subprocess

import pytest

from jarvis.cerebro_codex import CerebroCodex
from jarvis.config import Config
from jarvis.herramientas import Herramientas


def _completado(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=["codex", "exec"], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def herramientas(tmp_path):
    return Herramientas(tmp_path)


@pytest.fixture(autouse=True)
def _codex_instalado(monkeypatch):
    """Por defecto, simula que el binario de Codex CLI está en el PATH:
    no queremos que estas pruebas dependan de tener Codex instalado."""
    monkeypatch.setattr("jarvis.cerebro_codex.shutil.which", lambda _cmd: "/usr/local/bin/codex")


def test_sin_codex_instalado_falla_claro(monkeypatch, herramientas):
    monkeypatch.setattr("jarvis.cerebro_codex.shutil.which", lambda _cmd: None)

    with pytest.raises(RuntimeError, match="Codex CLI"):
        CerebroCodex(Config(), herramientas)


def test_responder_devuelve_el_texto_de_codex(herramientas):
    llamadas = []

    def ejecutor_falso(comando):
        llamadas.append(comando)
        return _completado(stdout="Son 42, señor.\n")

    cerebro = CerebroCodex(Config(), herramientas, ejecutar=ejecutor_falso)

    assert cerebro.responder("¿Cuánto es 6 por 7?") == "Son 42, señor."
    comando = llamadas[0]
    assert comando[:2] == ["codex", "exec"]
    prompt = comando[-1]
    assert "J.A.R.V.I.S." in prompt  # las instrucciones de Jarvis van en el prompt
    assert "¿Cuánto es 6 por 7?" in prompt


def test_responder_reenvia_la_conversacion_completa_en_cada_turno(herramientas):
    prompts = []

    def ejecutor_falso(comando):
        prompts.append(comando[-1])
        return _completado(stdout="ok")

    cerebro = CerebroCodex(Config(), herramientas, ejecutar=ejecutor_falso)
    cerebro.responder("hola")
    cerebro.responder("¿y ahora?")

    # El segundo prompt tiene que incluir el turno anterior completo.
    assert "hola" in prompts[1]
    assert "ok" in prompts[1]
    assert "¿y ahora?" in prompts[1]


def test_responder_sin_sesion_da_mensaje_amigable_no_crashea(herramientas):
    def ejecutor_falso(_comando):
        return _completado(returncode=1, stderr="Error: not logged in. Run `codex login`.")

    cerebro = CerebroCodex(Config(), herramientas, ejecutar=ejecutor_falso)

    assert "codex login" in cerebro.responder("hola").lower()


def test_responder_error_generico_no_crashea(herramientas):
    def ejecutor_falso(_comando):
        return _completado(returncode=1, stderr="boom")

    cerebro = CerebroCodex(Config(), herramientas, ejecutar=ejecutor_falso)

    assert "boom" in cerebro.responder("hola")


def test_responder_binario_desaparece_a_mitad_de_camino(herramientas):
    def ejecutor_falso(_comando):
        raise FileNotFoundError("codex")

    cerebro = CerebroCodex(Config(), herramientas, ejecutar=ejecutor_falso)

    assert "Codex CLI" in cerebro.responder("hola")


def test_responder_timeout_no_crashea(herramientas):
    def ejecutor_falso(_comando):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=120)

    cerebro = CerebroCodex(Config(), herramientas, ejecutar=ejecutor_falso)

    assert "tardando" in cerebro.responder("hola").lower()


def test_olvidar_limpia_el_historial(herramientas):
    cerebro = CerebroCodex(Config(), herramientas, ejecutar=lambda _c: _completado(stdout="ok"))
    cerebro.responder("hola")
    assert cerebro.historial

    cerebro.olvidar()
    assert cerebro.historial == []
