"""Pantalla 5 del wizard: resto de la instalación — descarga el bundle real
de Jarvis (del último release publicado, ver ../instalacion.py) y lo copia
al lugar de escritorio de este sistema."""

from __future__ import annotations

import threading

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ..instalacion import ErrorInstalacionJarvis, descargar_e_instalar


class PantallaInstalacion:
    """``al_continuar``: recibe la ruta real donde quedó instalado Jarvis
    (el .app en macOS, el .bat/.desktop en Windows/Linux) — la pantalla
    final (ver pantallas/final.py) la necesita para poder abrirlo."""

    def __init__(self, al_continuar):
        self._al_continuar = al_continuar
        self._resultado = None

        self._estado_label = toga.Label("", style=Pack(margin_top=12, margin_bottom=12))
        self._boton_instalar = toga.Button(
            "Instalar Jarvis", on_press=self._instalar, style=Pack(flex=1)
        )
        self._boton_continuar = toga.Button("Continuar", on_press=self._continuar, style=Pack(flex=1))
        self._fila_botones = toga.Box(
            style=Pack(direction=ROW, margin_top=10), children=[self._boton_instalar]
        )

        self.contenido = toga.Box(
            style=Pack(direction=COLUMN, margin=16, flex=1),
            children=[
                toga.Label("Instalar Jarvis", style=Pack(font_size=16, font_weight="bold", margin_bottom=8)),
                toga.Label(
                    "Último paso: descarga el programa real y lo deja listo para abrir.",
                    style=Pack(margin_bottom=16),
                ),
                self._estado_label,
                self._fila_botones,
            ],
        )

    def _instalar(self, widget) -> None:
        self._boton_instalar.enabled = False
        self._estado_label.text = "Preparando..."
        bucle = toga.App.app.loop

        def reportar(linea: str) -> None:
            bucle.call_soon_threadsafe(self._actualizar_progreso, linea)

        def trabajo() -> None:
            try:
                resultado = descargar_e_instalar(reportar=reportar)
            except ErrorInstalacionJarvis as error:
                bucle.call_soon_threadsafe(self._instalacion_fallo, str(error))
            else:
                bucle.call_soon_threadsafe(self._instalacion_lista, resultado)

        threading.Thread(target=trabajo, daemon=True).start()

    def _actualizar_progreso(self, linea: str) -> None:
        self._estado_label.text = linea

    def _instalacion_lista(self, resultado) -> None:
        self._resultado = resultado
        self._estado_label.text = "✓ Jarvis instalado."
        self._fila_botones.clear()
        self._fila_botones.add(self._boton_continuar)

    def _instalacion_fallo(self, mensaje: str) -> None:
        self._boton_instalar.enabled = True
        self._estado_label.text = f"La instalación falló: {mensaje}"

    def _continuar(self, widget) -> None:
        self._al_continuar(self._resultado)
