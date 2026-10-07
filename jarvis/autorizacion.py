"""Confirmación en dos pasos para herramientas irreversibles o sensibles.

Antes había dos copias casi iguales de esta lógica (cerrar_aplicacion en
sistema.py, recordar en herramientas.py) y se habían ido separando: la de
"recordar" exigía que el último mensaje del usuario sonara afirmativo, la de
"cerrar_aplicacion" no. Sin esa condición, una instrucción inyectada (p. ej.
desde una página web o un PDF que Jarvis lea) podía hacer que el modelo
llamara confirmado=true sin que el usuario hubiera dicho nada parecido a un
sí — el modelo controla ese parámetro, no prueba por sí solo que el usuario
confirmó. Una sola clase, usada por cualquier herramienta que necesite este
patrón, evita que una copia futura se quede corta como le pasó a esta.
"""

from __future__ import annotations

_PALABRAS_AFIRMATIVAS = {
    "si", "sí", "dale", "ok", "okay", "listo", "correcto", "exacto",
    "afirmativo", "confirmo", "claro", "obvio", "efectivamente", "simon",
}


def _suena_afirmativo(mensaje: str) -> bool:
    """Mira SOLO la primera palabra, nunca "¿aparece en algún lugar del
    mensaje?": un mensaje como "no, dale, mejor cancelá" contiene "dale"
    (está en la lista) pero no es un sí — es justo lo contrario."""
    palabras = mensaje.strip(".,!¿?¡ ").lower().split()
    if not palabras:
        return False
    primera = palabras[0].strip(".,!¿?¡")
    return primera in _PALABRAS_AFIRMATIVAS


class Autorizacion:
    """Registro de pedidos de confirmación pendientes, por clave arbitraria.

    Uso: la herramienta llama ``pedir(clave, turno_actual, confirmado,
    ultimo_mensaje_usuario)``. Si devuelve False, la acción todavía no está
    autorizada (la herramienta debe devolver un mensaje pidiéndole al
    usuario que confirme). Si devuelve True, la acción queda autorizada
    exactamente esta vez — el pendiente se borra, así que una llamada
    posterior con la misma clave vuelve a exigir todo el proceso.
    """

    def __init__(self) -> None:
        self._pendientes: dict[tuple, int] = {}

    def pedir(self, clave: tuple, turno_actual: int, confirmado: bool, ultimo_mensaje_usuario: str) -> bool:
        pedido_en = self._pendientes.get(clave)
        # Tres condiciones, no una: que el pedido sea justo del turno
        # ANTERIOR (no "en algún momento antes" — un pendiente viejo
        # colgado ahí podía quedar satisfecho por un "sí" de otro tema, en
        # otro turno, meses después); que lo que el usuario escribió en ese
        # turno exacto suene a un sí; y que "confirmado=true" lo diga el
        # modelo (no prueba nada por sí solo, es la entrada que controla el
        # modelo, no el usuario — por eso las otras dos condiciones).
        autorizada = (
            confirmado
            and pedido_en is not None
            and pedido_en == turno_actual - 1
            and _suena_afirmativo(ultimo_mensaje_usuario)
        )
        if autorizada:
            del self._pendientes[clave]
            return True
        # setdefault, NO reemplazo incondicional: si ya hay un pedido
        # pendiente para esta clave, su turno original NO se renueva. Sin
        # esto, el modelo podía reintentar confirmado=true en cada turno
        # sucesivo hasta que el usuario dijera "sí" por cualquier motivo no
        # relacionado — cada intento fallido corría la ventana "turno
        # siguiente" hacia adelante, dejando la ligazón al pedido original
        # sin efecto.
        self._pendientes.setdefault(clave, turno_actual)
        return False
