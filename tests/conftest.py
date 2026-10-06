"""Fixtures compartidas por toda la suite."""

import pytest


@pytest.fixture(autouse=True)
def _sin_ventana_nativa_por_defecto(monkeypatch):
    """Los tests no deben disparar la ventana flotante real (AppKit bloquea
    con app.run()). Este Mac tiene PyObjC instalado, así que sin esto
    cualquier test con --hud/modo voz terminaría abriendo una ventana de
    verdad y colgándose. Los tests que sí prueban el camino nativo
    sobreescriben esto explícitamente."""
    monkeypatch.setattr("jarvis.hud.ventana_macos.disponible", lambda: False)


@pytest.fixture(autouse=True)
def _env_aislado_de_la_maquina_real(monkeypatch, tmp_path):
    """``jarvis.config`` lee ``~/.jarvis/.env`` como fallback (para que el
    menú funcione también sin terminal, ver ``_RUTA_ENV_POR_DEFECTO``). Sin
    esto, la suite leería el ``.env`` REAL de la máquina donde corre — en
    desarrollo, poblado por pruebas manuales — y un test que no mockea
    explícitamente el proveedor/motor podría terminar usando la sesión real
    (Codex/Claude) en vez del cliente falso que preparó. Un test que sí
    quiera probar el fallback real puede sobreescribir esto."""
    monkeypatch.setattr("jarvis.config._RUTA_ENV_POR_DEFECTO", tmp_path / ".env-aislado-de-tests")
