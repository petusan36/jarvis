"""Pantalla 4 del wizard: selección de modelo local, usando el hardware ya
escaneado en la pantalla anterior (``InfoHardware``, ver pantallas/hardware.py)
para recomendar uno.

Si Ollama ya tiene modelos instalados (lo más probable si el usuario lo
tenía de antes, o si una corrida anterior de este mismo instalador ya bajó
uno), se prefiere reusar el más grande que entre en el hardware en vez de
empujar una descarga nueva por reflejo — ver ``modelos.mejor_modelo``."""

from __future__ import annotations

import threading

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ..hardware import InfoHardware
from ..modelos import (
    MODELOS_DISPONIBLES,
    ErrorDescargaModelo,
    descargar_modelo,
    listar_modelos_instalados,
    mejor_modelo,
)


class PantallaModelo:
    """``al_continuar``: callback sin argumentos, solo alcanzable con un
    modelo ya instalado o recién descargado con éxito."""

    def __init__(self, info_hardware: InfoHardware, al_continuar):
        self._al_continuar = al_continuar
        self._instalados = listar_modelos_instalados()
        self._tag_elegido, ya_instalado = mejor_modelo(info_hardware.ram_total_gb, self._instalados)

        self._estado_label = toga.Label("", style=Pack(margin_top=12, margin_bottom=12))
        self._boton_descargar = toga.Button(
            "Descargar este modelo", on_press=self._descargar, style=Pack(flex=1)
        )
        self._boton_continuar = toga.Button("Continuar", on_press=self._continuar, style=Pack(flex=1))
        self._fila_botones = toga.Box(style=Pack(direction=ROW, margin_top=10))

        self._lista_modelos = toga.Box(style=Pack(direction=COLUMN, margin_bottom=8))
        self._botones_modelo: dict[str, toga.Button] = {}
        for opcion in MODELOS_DISPONIBLES:
            etiquetas = []
            if opcion.tag in self._instalados:
                etiquetas.append("ya instalado")
            if opcion.tag == self._tag_elegido:
                etiquetas.append("recomendado para este equipo")
            marca = f" ({', '.join(etiquetas)})" if etiquetas else ""
            boton = toga.Button(
                f"{opcion.tag} — {opcion.tamano_gb} GB{marca}",
                on_press=self._elegir_modelo, style=Pack(margin_bottom=4),
            )
            boton.tag_modelo = opcion.tag
            self._botones_modelo[opcion.tag] = boton
            self._lista_modelos.add(boton)

        self.contenido = toga.Box(
            style=Pack(direction=COLUMN, margin=16, flex=1),
            children=[
                toga.Label("Modelo local", style=Pack(font_size=16, font_weight="bold", margin_bottom=8)),
                toga.Label(
                    "Elegido según el hardware de este equipo y lo que ya tenés instalado. "
                    "Podés elegir otro de la lista si preferís.",
                    style=Pack(margin_bottom=16),
                ),
                self._lista_modelos,
                self._estado_label,
                self._fila_botones,
            ],
        )
        self._actualizar_seleccion()
        if ya_instalado:
            self._descarga_lista()
        else:
            self._mostrar_boton_descargar()

    def _elegir_modelo(self, widget) -> None:
        self._tag_elegido = widget.tag_modelo
        self._actualizar_seleccion()
        if self._tag_elegido in self._instalados:
            self._descarga_lista()
        else:
            self._mostrar_boton_descargar()

    def _actualizar_seleccion(self) -> None:
        for tag, boton in self._botones_modelo.items():
            boton.style.font_weight = "bold" if tag == self._tag_elegido else "normal"

    def _mostrar_boton_descargar(self) -> None:
        self._fila_botones.clear()
        self._fila_botones.add(self._boton_descargar)
        self._estado_label.text = f"Modelo elegido: {self._tag_elegido} (hace falta descargarlo)"

    def _descargar(self, widget) -> None:
        self._boton_descargar.enabled = False
        for boton in self._botones_modelo.values():
            boton.enabled = False
        self._estado_label.text = f"Descargando {self._tag_elegido}..."
        bucle = toga.App.app.loop
        tag = self._tag_elegido

        def reportar(linea: str) -> None:
            bucle.call_soon_threadsafe(self._actualizar_progreso, linea)

        def trabajo() -> None:
            try:
                descargar_modelo(tag, reportar=reportar)
            except ErrorDescargaModelo as error:
                bucle.call_soon_threadsafe(self._descarga_fallo, str(error))
            else:
                bucle.call_soon_threadsafe(self._descarga_lista)

        threading.Thread(target=trabajo, daemon=True).start()

    def _actualizar_progreso(self, linea: str) -> None:
        self._estado_label.text = linea

    def _descarga_lista(self) -> None:
        if self._tag_elegido not in self._instalados:
            self._instalados.append(self._tag_elegido)
        self._estado_label.text = f"✓ {self._tag_elegido} listo para usar."
        self._fila_botones.clear()
        self._fila_botones.add(self._boton_continuar)

    def _descarga_fallo(self, mensaje: str) -> None:
        for boton in self._botones_modelo.values():
            boton.enabled = True
        self._boton_descargar.enabled = True
        self._estado_label.text = f"La descarga falló: {mensaje}"

    def _continuar(self, widget) -> None:
        self._al_continuar()
