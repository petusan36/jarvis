"""Pantalla 6 (última) del wizard: abrir Jarvis ahora, o solo cerrar el
instalador. Última pantalla del flujo fijo — no hay paso después de esta."""

from __future__ import annotations

from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ..instalacion import abrir_jarvis


class PantallaFinal:
    """``al_cerrar``: callback sin argumentos que decide cómo termina el
    wizard (ver app.py) — esta clase no sabe si eso significa terminar el
    proceso entero o solo cerrar una ventana."""

    def __init__(self, resultado_instalacion: Path, al_cerrar):
        self._resultado = resultado_instalacion
        self._al_cerrar = al_cerrar

        boton_abrir = toga.Button("Abrir Jarvis", on_press=self._abrir, style=Pack(flex=1))
        boton_cerrar = toga.Button("Cerrar", on_press=self._cerrar, style=Pack(flex=1))
        fila_botones = toga.Box(
            style=Pack(direction=ROW, margin_top=10), children=[boton_abrir, boton_cerrar]
        )

        self.contenido = toga.Box(
            style=Pack(direction=COLUMN, margin=16, flex=1),
            children=[
                toga.Label("Listo", style=Pack(font_size=16, font_weight="bold", margin_bottom=8)),
                toga.Label(
                    "Jarvis ya está instalado. Podés abrirlo ahora o cerrar este instalador.",
                    style=Pack(margin_bottom=16),
                ),
                fila_botones,
            ],
        )

    def _abrir(self, widget) -> None:
        abrir_jarvis(self._resultado)
        self._al_cerrar()

    def _cerrar(self, widget) -> None:
        self._al_cerrar()
