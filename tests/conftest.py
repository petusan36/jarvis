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
