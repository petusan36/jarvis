"""Pruebas de CerebroCodex: todas con un ejecutor falso, sin invocar el
binario real de Codex CLI. El ejecutor falso escribe en el archivo que
recibe con -o (igual que haría codex exec de verdad) y devuelve stdout
en formato JSONL, como con --json."""

from __future__ import annotations

import json
import subprocess

import pytest

from jarvis.cerebro_codex import CerebroCodex
from jarvis.config import Config
from jarvis.herramientas import Herramientas


def _ruta_salida(comando: list[str]) -> str:
    return comando[comando.index("-o") + 1]


def _jsonl_inicio(thread_id: str) -> str:
    eventos = [
        {"type": "thread.started", "thread_id": thread_id},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "x"}},
        {"type": "turn.completed", "usage": {"input_tokens": 1}},
    ]
    return "\n".join(json.dumps(e) for e in eventos) + "\n"


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


def test_primer_turno_arranca_sesion_nueva_y_lee_el_archivo_de_salida(herramientas):
    comandos = []

    def ejecutor_falso(comando):
        comandos.append(comando)
        with open(_ruta_salida(comando), "w", encoding="utf-8") as archivo:
            archivo.write("Son 42, señor.")
        return _completado(stdout=_jsonl_inicio("sesion-1"))

    cerebro = CerebroCodex(Config(), herramientas, ejecutar=ejecutor_falso)

    assert cerebro.responder("¿Cuánto es 6 por 7?") == "Son 42, señor."
    comando = comandos[0]
    assert comando[:2] == ["codex", "exec"]
    assert "resume" not in comando
    assert "--sandbox" in comando
    assert "--json" in comando
    prompt = comando[-1]
    assert "J.A.R.V.I.S." in prompt  # las instrucciones de Jarvis van en el primer prompt
    assert "¿Cuánto es 6 por 7?" in prompt


def test_segundo_turno_usa_resume_con_el_session_id_capturado(herramientas):
    comandos = []

    def ejecutor_falso(comando):
        comandos.append(comando)
        with open(_ruta_salida(comando), "w", encoding="utf-8") as archivo:
            archivo.write("ok")
        return _completado(stdout=_jsonl_inicio("sesion-abc"))

    cerebro = CerebroCodex(Config(), herramientas, ejecutar=ejecutor_falso)
    cerebro.responder("hola")
    cerebro.responder("¿y ahora?")

    segundo_comando = comandos[1]
    assert segundo_comando[:4] == ["codex", "exec", "resume", "sesion-abc"]
    assert "--sandbox" not in segundo_comando  # resume no acepta ese flag
    assert segundo_comando[-1] == "¿y ahora?"  # no se reenvía todo el historial como texto


def test_olvidar_arranca_sesion_nueva_en_el_siguiente_turno(herramientas):
    comandos = []

    def ejecutor_falso(comando):
        comandos.append(comando)
        with open(_ruta_salida(comando), "w", encoding="utf-8") as archivo:
            archivo.write("ok")
        return _completado(stdout=_jsonl_inicio("sesion-1"))

    cerebro = CerebroCodex(Config(), herramientas, ejecutar=ejecutor_falso)
    cerebro.responder("hola")
    cerebro.olvidar()
    cerebro.responder("hola de nuevo")

    assert "resume" not in comandos[1]  # tras olvidar(), vuelve a ser un primer turno


def test_responder_ignora_el_banner_y_solo_lee_el_archivo_de_salida(herramientas):
    """Aunque stdout venga con el banner/JSONL completo, la respuesta debe
    salir del archivo -o, nunca de stdout."""

    def ejecutor_falso(comando):
        with open(_ruta_salida(comando), "w", encoding="utf-8") as archivo:
            archivo.write("respuesta limpia")
        return _completado(stdout="basura de banner\n" + _jsonl_inicio("sesion-1") + "más basura")

    cerebro = CerebroCodex(Config(), herramientas, ejecutar=ejecutor_falso)

    assert cerebro.responder("hola") == "respuesta limpia"


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


def test_archivo_temporal_de_salida_se_borra_despues_de_leerlo(herramientas):
    rutas = []

    def ejecutor_falso(comando):
        ruta = _ruta_salida(comando)
        rutas.append(ruta)
        with open(ruta, "w", encoding="utf-8") as archivo:
            archivo.write("ok")
        return _completado(stdout=_jsonl_inicio("sesion-1"))

    cerebro = CerebroCodex(Config(), herramientas, ejecutar=ejecutor_falso)
    cerebro.responder("hola")

    import os

    assert not os.path.exists(rutas[0])
