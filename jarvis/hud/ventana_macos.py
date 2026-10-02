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


def ejecutar_con_ventana_flotante(url: str, trabajo: Callable[[], None]) -> None:
    """Muestra la ventana y corre ``trabajo`` (el bucle de conversación) en un
    hilo aparte, mientras el hilo principal corre el bucle de eventos de
    Cocoa (lo exige AppKit). Vuelve cuando ``trabajo`` termina."""
    import AppKit

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)  # sin ícono en el Dock
    _ventana = _crear_ventana(url)  # noqa: F841 — referencia viva, que no la recoja el GC

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
