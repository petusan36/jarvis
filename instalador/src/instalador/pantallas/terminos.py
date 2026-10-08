"""Pantalla 1 del wizard: Términos y Condiciones.

Primera pantalla, sin excepción — nada de escaneo de hardware ni de
instalación corre antes de que el usuario acepte explícitamente. El texto
cubre el consentimiento amplio que Jarvis necesita para funcionar como
asistente real de PC: ejecutar comandos de shell, abrir y manejar
aplicaciones instaladas, crear y modificar archivos/código. Ese
consentimiento se pide UNA vez, acá, no en cada acción individual (decisión
ya tomada para la app en sí: ver jarvis/sistema.py).
"""

from __future__ import annotations

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

TEXTO_TERMINOS = """\
Jarvis es un asistente personal que corre en tu computador y que vos \
controlás por voz o por texto. Para que funcione como un asistente real, \
necesita permisos amplios sobre este equipo. Antes de instalar, leé esto \
con atención:

QUÉ PUEDE HACER JARVIS EN TU EQUIPO

- Ejecutar comandos de shell (instalar paquetes, correr scripts, manipular \
archivos) con tu confirmación para las acciones destructivas.
- Abrir, cerrar y controlar aplicaciones ya instaladas en tu equipo.
- Crear, leer y modificar archivos dentro de tu carpeta personal (y, al \
ejecutar comandos, potencialmente fuera de ella).
- Escribir código y abrir un entorno de desarrollo para armar proyectos \
que vos le pidas.
- Escuchar tu voz por el micrófono para responderte, y usar reconocimiento \
de hablante para distinguir tu voz de la de otras personas (podés \
desactivarlo después).
- Guardar datos que vos le compartas (preferencias, notas) para \
recordarlos en conversaciones futuras.

QUÉ NO HACE

- Jarvis no manda tus datos a servidores de terceros salvo que vos elijas \
un proveedor de IA en la nube (Claude o Codex) para conversar — en ese \
caso, tus mensajes viajan a ese proveedor, como con cualquier asistente \
basado en IA. Con un modelo local (Ollama), nada sale de tu equipo.
- Jarvis no actúa sin que se lo pidas: no inicia acciones por su cuenta.

TU RESPONSABILIDAD

Al aceptar, entendés que le estás dando a Jarvis la capacidad de modificar \
archivos y ejecutar comandos en tu equipo. Usalo en un equipo donde estés \
cómodo con ese nivel de acceso. Las acciones que pueden borrar o destruir \
algo te van a pedir confirmación explícita en el momento, pero el resto \
corre con la autorización general que das acá.

Si no aceptás estos términos, el instalador se cierra sin instalar nada.\
"""


class PantallaTerminos:
    """Construye el contenido de la pantalla y conecta sus botones.

    ``al_aceptar``/``al_rechazar``: callbacks sin argumentos que decide el
    controlador del wizard (``app.py``) — esta clase no sabe qué pantalla
    viene después ni cómo cerrar la app, solo construye su UI y reacciona
    a los dos únicos resultados posibles de esta pantalla."""

    def __init__(self, al_aceptar, al_rechazar):
        self._al_aceptar = al_aceptar
        self._al_rechazar = al_rechazar
        self._checkbox = toga.Switch("Leí y acepto los términos y condiciones")
        self._checkbox.on_change = self._actualizar_boton_continuar

        self._boton_continuar = toga.Button(
            "Continuar", on_press=self._continuar, style=Pack(flex=1)
        )
        self._boton_continuar.enabled = False
        boton_rechazar = toga.Button(
            "Rechazar y salir", on_press=self._rechazar, style=Pack(flex=1)
        )

        texto = toga.MultilineTextInput(value=TEXTO_TERMINOS, readonly=True, style=Pack(flex=1))

        fila_botones = toga.Box(
            style=Pack(direction=ROW, margin_top=10),
            children=[boton_rechazar, self._boton_continuar],
        )

        self.contenido = toga.Box(
            style=Pack(direction=COLUMN, margin=16, flex=1),
            children=[
                toga.Label("Términos y condiciones", style=Pack(font_size=16, font_weight="bold", margin_bottom=8)),
                texto,
                self._checkbox,
                fila_botones,
            ],
        )

    def _actualizar_boton_continuar(self, widget) -> None:
        self._boton_continuar.enabled = self._checkbox.value

    def _continuar(self, widget) -> None:
        if self._checkbox.value:
            self._al_aceptar()

    def _rechazar(self, widget) -> None:
        self._al_rechazar()
