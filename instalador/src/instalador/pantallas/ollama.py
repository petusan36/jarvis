"""Pantalla 2 del wizard: Ollama es requisito, no opcional — si no está
instalado, no hay forma de avanzar desde acá salvo instalarlo (o cerrar el
instalador)."""

from __future__ import annotations

import threading

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ..ollama import ErrorInstalacionOllama, instalar_automatico_disponible, instalar_ollama, ollama_instalado


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
        if not instalar_automatico_disponible():
            self._estado_label.text = (
                "La instalación automática no está disponible en este sistema operativo "
                "todavía. Instalá Ollama manualmente desde https://ollama.com y volvé a "
                "verificar."
            )
            return

        self._boton_instalar.enabled = False
        self._boton_verificar.enabled = False
        self._estado_label.text = "Instalando Ollama..."
        bucle = toga.App.app.loop

        def reportar(linea: str) -> None:
            bucle.call_soon_threadsafe(self._actualizar_progreso, linea)

        def trabajo() -> None:
            try:
                instalar_ollama(reportar=reportar)
            except ErrorInstalacionOllama as error:
                bucle.call_soon_threadsafe(self._instalacion_fallo, str(error))
            else:
                bucle.call_soon_threadsafe(self._instalacion_lista)

        threading.Thread(target=trabajo, daemon=True).start()

    def _actualizar_progreso(self, linea: str) -> None:
        self._estado_label.text = linea

    def _instalacion_lista(self) -> None:
        self._boton_instalar.enabled = True
        self._boton_verificar.enabled = True
        self._actualizar_estado()

    def _instalacion_fallo(self, mensaje: str) -> None:
        self._boton_instalar.enabled = True
        self._boton_verificar.enabled = True
        self._estado_label.text = f"La instalación falló: {mensaje}"

    def _continuar(self, widget) -> None:
        self._al_continuar()
