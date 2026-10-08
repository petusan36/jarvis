"""Pantalla 3 del wizard: escaneo de hardware. Corre DESPUÉS de aceptar los
términos y de resolver Ollama, nunca antes — orden fijo del wizard, no hay
forma de llegar acá sin pasar por las dos pantallas anteriores (ver
app.py)."""

from __future__ import annotations

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ..hardware import InfoHardware, escanear_hardware


class PantallaHardware:
    """``al_continuar``: recibe la ``InfoHardware`` escaneada, para que la
    siguiente pantalla (selección de modelo) la use sin tener que volver a
    escanear."""

    def __init__(self, al_continuar):
        self._al_continuar = al_continuar
        self._info: InfoHardware = escanear_hardware()

        gpu_texto = self._info.gpu_nombre or "no se pudo determinar"
        resumen = toga.Box(
            style=Pack(direction=COLUMN, margin_bottom=16),
            children=[
                toga.Label(f"Núcleos de CPU: {self._info.nucleos_cpu}"),
                toga.Label(f"RAM total: {self._info.ram_total_gb} GB"),
                toga.Label(f"GPU: {gpu_texto}"),
            ],
        )

        boton_continuar = toga.Button("Continuar", on_press=self._continuar, style=Pack(flex=1))
        fila_botones = toga.Box(style=Pack(direction=ROW, margin_top=10), children=[boton_continuar])

        self.contenido = toga.Box(
            style=Pack(direction=COLUMN, margin=16, flex=1),
            children=[
                toga.Label("Hardware detectado", style=Pack(font_size=16, font_weight="bold", margin_bottom=8)),
                toga.Label(
                    "Esto se usa para recomendar qué modelo local correr mejor en este equipo.",
                    style=Pack(margin_bottom=16),
                ),
                resumen,
                fila_botones,
            ],
        )

    def _continuar(self, widget) -> None:
        self._al_continuar(self._info)
