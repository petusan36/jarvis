"""Pantalla 2 del wizard: Ollama es requisito, no opcional — si no está
instalado, no hay forma de avanzar desde acá salvo instalarlo (o cerrar el
instalador). Esta pantalla solo detecta; el botón que dispara la
instalación real por sistema operativo es el siguiente incremento (hace
falta verificar el mecanismo real de instalación por SO antes de
escribirlo — no se va a inventar un comando sin confirmarlo)."""

from __future__ import annotations

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ..ollama import ollama_instalado


class PantallaOllama:
    """``al_continuar``: callback sin argumentos, solo alcanzable si Ollama
    está instalado. No hay camino para "saltear" esta pantalla sin Ollama:
    bloquea el avance a propósito (roadmap, punto 5)."""

    def __init__(self, al_continuar):
        self._al_continuar = al_continuar

        self._estado_label = toga.Label("", style=Pack(font_size=14, margin_bottom=12))
        self._boton_continuar = toga.Button(
            "Continuar", on_press=self._continuar, style=Pack(flex=1)
        )
        self._boton_verificar = toga.Button(
            "Verificar de nuevo", on_press=self._verificar, style=Pack(flex=1)
        )
        self._boton_instalar = toga.Button(
            "Instalar Ollama", on_press=self._instalar, style=Pack(flex=1)
        )

        fila_botones = toga.Box(style=Pack(direction=ROW, margin_top=10))

        self.contenido = toga.Box(
            style=Pack(direction=COLUMN, margin=16, flex=1),
            children=[
                toga.Label("Modelo local: Ollama", style=Pack(font_size=16, font_weight="bold", margin_bottom=8)),
                toga.Label(
                    "Jarvis necesita Ollama instalado en este equipo para correr modelos de "
                    "IA en local. Es un requisito para seguir, no un paso opcional.",
                    style=Pack(margin_bottom=16),
                ),
                self._estado_label,
                fila_botones,
            ],
        )
        self._fila_botones = fila_botones
        self._actualizar_estado()

    def _actualizar_estado(self) -> None:
        instalado = ollama_instalado()
        self._fila_botones.clear()
        if instalado:
            self._estado_label.text = "✓ Ollama está instalado."
            self._fila_botones.add(self._boton_continuar)
        else:
            self._estado_label.text = "✗ Ollama no está instalado todavía."
            self._fila_botones.add(self._boton_instalar)
            self._fila_botones.add(self._boton_verificar)

    def _verificar(self, widget) -> None:
        self._actualizar_estado()

    def _instalar(self, widget) -> None:
        # Siguiente incremento: disparar el instalador real de Ollama por
        # sistema operativo. Por ahora solo re-verifica, para no inventar
        # un mecanismo de instalación sin confirmarlo contra lo que Ollama
        # realmente distribuye en cada SO.
        self._estado_label.text = (
            "Instalación automática todavía no implementada: instalá Ollama manualmente "
            "desde https://ollama.com y volvé a verificar."
        )

    def _continuar(self, widget) -> None:
        self._al_continuar()
