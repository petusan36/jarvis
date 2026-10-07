"""Ventana flotante nativa para el HUD en macOS: sin marco, sin botones,
fondo transparente, siempre encima — como un widget sobre el escritorio.

Usa PyObjC (AppKit + WebKit) para alojar la misma página que, en otros
sistemas, se abre en una ventana de Chrome (ver ``hud.__init__._abrir_ventana_app``).
Si algo acá falla o no aplica (no es macOS, falta PyObjC), quien llama debe
caer a ese otro camino — este módulo no tiene fallback propio.
"""

from __future__ import annotations

import sys
import threading
from typing import Callable

MARGEN = 24  # separación de los bordes de pantalla, en puntos
FRACCION_PANTALLA = 0.18  # lado de la ventana, como fracción del ancho de pantalla
TAMANO_MINIMO = 260
TAMANO_MAXIMO = 520


def disponible() -> bool:
    """¿Se puede intentar la ventana nativa en este sistema?"""
    if sys.platform != "darwin":
        return False
    try:
        import AppKit  # noqa: F401
        import WebKit  # noqa: F401
    except ImportError:
        return False
    return True


def calcular_geometria(ancho_pantalla: float, alto_pantalla: float) -> tuple[float, float, float, float]:
    """(x, y, ancho, alto) de la ventana: cuadrada, proporcional a la pantalla
    principal, arriba a la izquierda con margen fijo. Cocoa mide "y" desde
    abajo, así que "arriba" es ``alto_pantalla - alto - margen``."""
    lado = min(max(ancho_pantalla * FRACCION_PANTALLA, TAMANO_MINIMO), TAMANO_MAXIMO)
    x = MARGEN
    y = alto_pantalla - lado - MARGEN
    return x, y, lado, lado


def _crear_ventana(url: str):
    """Construye y muestra la ventana flotante. Debe llamarse en el hilo principal."""
    import AppKit
    import WebKit
    from Foundation import NSURL, NSURLRequest

    pantalla = AppKit.NSScreen.mainScreen().frame()
    x, y, ancho, alto = calcular_geometria(pantalla.size.width, pantalla.size.height)
    marco = AppKit.NSMakeRect(x, y, ancho, alto)

    ventana = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        marco, AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False,
    )
    ventana.setBackgroundColor_(AppKit.NSColor.clearColor())
    ventana.setOpaque_(False)
    ventana.setHasShadow_(True)
    ventana.setLevel_(AppKit.NSFloatingWindowLevel)
    ventana.setMovableByWindowBackground_(True)
    ventana.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces)
    ventana.setIgnoresMouseEvents_(False)

    vista = WebKit.WKWebView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, ancho, alto))
    try:
        vista.setValue_forKey_(False, "drawsBackground")  # fondo del webview también transparente
    except (KeyError, AttributeError):
        pass  # mejor esfuerzo: en el peor caso queda con el fondo blanco del webview
    vista.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))

    ventana.setContentView_(vista)
    ventana.makeKeyAndOrderFront_(None)
    return ventana


_ventana_flotante_activa = None  # referencia global: solo hay una ventana del HUD por proceso


def ejecutar_con_ventana_flotante(url: str, trabajo: Callable[[], None]) -> None:
    """Muestra la ventana y corre ``trabajo`` (el bucle de conversación) en un
    hilo aparte, mientras el hilo principal corre el bucle de eventos de
    Cocoa (lo exige AppKit). Vuelve cuando ``trabajo`` termina."""
    global _ventana_flotante_activa
    import AppKit

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)  # sin ícono en el Dock
    _ventana_flotante_activa = _crear_ventana(url)
    try:
        _correr_trabajo_y_terminar(app, trabajo)
    finally:
        _ventana_flotante_activa = None


def ocultar_ventana() -> None:
    """Oculta la ventana flotante del HUD (modo de escucha pasiva, ver
    jarvis.voz.oido.Oido.dormir). No hace nada si no hay ventana nativa
    activa (modo texto, u otro sistema operativo) — mismo "mejor esfuerzo,
    sin romper nada" que el resto de este módulo."""
    if _ventana_flotante_activa is not None:
        _ventana_flotante_activa.performSelectorOnMainThread_withObject_waitUntilDone_(
            "orderOut:", None, False,
        )


def mostrar_ventana() -> None:
    """Vuelve a mostrar la ventana flotante del HUD tras ocultar_ventana()."""
    if _ventana_flotante_activa is not None:
        _ventana_flotante_activa.performSelectorOnMainThread_withObject_waitUntilDone_(
            "makeKeyAndOrderFront:", None, False,
        )


ANCHO_MENU = 480
ALTO_MENU = 420


def _crear_ventana_menu(url: str):
    """Como ``_crear_ventana``, pero una ventana normal (con título y botón
    de cerrar, centrada en pantalla) en vez del widget flotante sin marco
    del HUD: el menú de conexión con IA necesita que el usuario haga click
    y foco con normalidad, no que flote encima de todo."""
    import AppKit
    import WebKit
    from Foundation import NSURL, NSURLRequest

    pantalla = AppKit.NSScreen.mainScreen().frame()
    ancho, alto = ANCHO_MENU, ALTO_MENU
    x = (pantalla.size.width - ancho) / 2
    y = (pantalla.size.height - alto) / 2
    marco = AppKit.NSMakeRect(x, y, ancho, alto)

    estilo = AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable
    ventana = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        marco, estilo, AppKit.NSBackingStoreBuffered, False,
    )
    ventana.setTitle_("Jarvis")
    ventana.setLevel_(AppKit.NSNormalWindowLevel)

    vista = WebKit.WKWebView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, ancho, alto))
    vista.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))

    ventana.setContentView_(vista)
    ventana.makeKeyAndOrderFront_(None)
    return ventana


def ejecutar_ventana_menu(url: str, trabajo: Callable[[], None]) -> None:
    """Como ``ejecutar_con_ventana_flotante``, pero con la ventana normal de
    ``_crear_ventana_menu`` — y, a diferencia de esa, VUELVE de verdad:
    cuando ``trabajo`` termina, cierra solo la ventana (``NSApp.stop_`` +
    un evento para despertar el run loop) en vez de terminar el proceso
    entero con ``terminate:``. Hace falta así porque, después del menú, el
    mismo proceso de Python tiene que seguir (crear el "cerebro" con el
    motor elegido y arrancar el modo voz/HUD de siempre) — no es la última
    ventana del programa, como sí lo es la del HUD."""
    import AppKit

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)  # con ícono en el Dock: es la app visible
    ventana = _crear_ventana_menu(url)
    app.activateIgnoringOtherApps_(True)

    def _trabajo_y_cerrar_ventana() -> None:
        try:
            trabajo()
        finally:
            ventana.performSelectorOnMainThread_withObject_waitUntilDone_(
                "orderOut:", None, False,
            )
            app.stop_(None)
            # app.stop_ solo marca una bandera que el run loop revisa en el
            # próximo evento: sin esto, si no llega ningún evento real
            # (ej. el usuario no mueve el mouse), app.run() nunca vuelve.
            evento_despertador = AppKit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
                AppKit.NSEventTypeApplicationDefined, (0, 0), 0, 0, 0, None, 0, 0, 0,
            )
            app.postEvent_atStart_(evento_despertador, True)

    hilo = threading.Thread(target=_trabajo_y_cerrar_ventana, daemon=True)
    hilo.start()
    app.run()
    ventana.close()


def _correr_trabajo_y_terminar(app, trabajo: Callable[[], None]) -> None:
    """Corre ``trabajo`` en un hilo aparte mientras el hilo principal corre
    el bucle de eventos de Cocoa (lo exige AppKit), y termina ese bucle
    cuando ``trabajo`` vuelve, cierre o lance lo que lance."""
    import AppKit

    def _trabajo_y_cerrar() -> None:
        try:
            trabajo()
        finally:
            AppKit.NSApp.performSelectorOnMainThread_withObject_waitUntilDone_(
                "terminate:", None, False,
            )

    hilo = threading.Thread(target=_trabajo_y_cerrar, daemon=True)
    hilo.start()
    app.run()
