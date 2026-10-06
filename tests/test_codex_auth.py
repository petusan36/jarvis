"""Pruebas de leer_token_codex: lectura y vencimiento del access_token de
~/.codex/auth.json, sin tocar el archivo real del usuario."""

from __future__ import annotations

import base64
import json
import time

import pytest

from jarvis.proveedores.codex_responses_adaptador import leer_token_codex


def _jwt(payload: dict) -> str:
    """Construye un JWT de juguete (sin firma real: a leer_token_codex no
    le importa, solo decodifica el payload)."""
    def _parte(datos: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(datos).encode()).decode().rstrip("=")

    return f"{_parte({'alg': 'none'})}.{_parte(payload)}.firma-falsa"


def _escribir_auth(ruta, token: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"tokens": {"access_token": token}}), encoding="utf-8")


def test_lee_el_token_vigente(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    token = _jwt({"exp": int(time.time()) + 3600})
    _escribir_auth(tmp_path / "auth.json", token)

    assert leer_token_codex() == token


def test_sin_archivo_de_sesion_pide_login(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    with pytest.raises(RuntimeError, match="codex login"):
        leer_token_codex()


def test_token_vencido_pide_login_de_nuevo(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    token = _jwt({"exp": int(time.time()) - 3600})
    _escribir_auth(tmp_path / "auth.json", token)

    with pytest.raises(RuntimeError, match="venció"):
        leer_token_codex()


def test_archivo_corrupto_da_error_claro(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "auth.json").write_text("esto no es json", encoding="utf-8")

    with pytest.raises(RuntimeError):
        leer_token_codex()


def test_sin_campo_exp_se_acepta_igual(tmp_path, monkeypatch):
    """Un JWT sin 'exp' no puede evaluarse como vencido: se deja pasar en
    vez de bloquear al usuario con un falso vencimiento."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    token = _jwt({"sub": "usuario-sin-exp"})
    _escribir_auth(tmp_path / "auth.json", token)

    assert leer_token_codex() == token
