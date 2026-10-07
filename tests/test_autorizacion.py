"""Pruebas de jarvis.autorizacion: el gate de confirmación compartido."""

from jarvis.autorizacion import Autorizacion


def test_primera_llamada_queda_pendiente():
    autorizacion = Autorizacion()
    assert not autorizacion.pedir(("x",), turno_actual=1, confirmado=True, ultimo_mensaje_usuario="sí")


def test_confirmar_en_el_mismo_turno_no_alcanza():
    autorizacion = Autorizacion()
    autorizacion.pedir(("x",), turno_actual=1, confirmado=False, ultimo_mensaje_usuario="")
    assert not autorizacion.pedir(("x",), turno_actual=1, confirmado=True, ultimo_mensaje_usuario="sí")


def test_confirmar_en_el_turno_siguiente_con_un_si_autoriza():
    autorizacion = Autorizacion()
    autorizacion.pedir(("x",), turno_actual=1, confirmado=False, ultimo_mensaje_usuario="")
    assert autorizacion.pedir(("x",), turno_actual=2, confirmado=True, ultimo_mensaje_usuario="sí, dale")


def test_sin_mensaje_afirmativo_no_autoriza_aunque_confirmado_sea_true():
    autorizacion = Autorizacion()
    autorizacion.pedir(("x",), turno_actual=1, confirmado=False, ultimo_mensaje_usuario="")
    assert not autorizacion.pedir(("x",), turno_actual=2, confirmado=True, ultimo_mensaje_usuario="¿qué hora es?")


def test_negacion_que_contiene_una_palabra_afirmativa_no_autoriza():
    autorizacion = Autorizacion()
    autorizacion.pedir(("x",), turno_actual=1, confirmado=False, ultimo_mensaje_usuario="")
    mensaje = "no, dale, mejor cancelá eso"
    assert not autorizacion.pedir(("x",), turno_actual=2, confirmado=True, ultimo_mensaje_usuario=mensaje)


def test_turno_viejo_no_queda_satisfecho_por_un_si_de_otro_tema_mucho_despues():
    autorizacion = Autorizacion()
    autorizacion.pedir(("x",), turno_actual=1, confirmado=False, ultimo_mensaje_usuario="")
    # el usuario responde cosas no relacionadas en varios turnos...
    autorizacion.pedir(("x",), turno_actual=2, confirmado=True, ultimo_mensaje_usuario="¿y mañana?")
    autorizacion.pedir(("x",), turno_actual=3, confirmado=True, ultimo_mensaje_usuario="¿y pasado?")
    # ...y mucho después dice que sí, pero ya no es el turno siguiente al pedido original
    assert not autorizacion.pedir(("x",), turno_actual=10, confirmado=True, ultimo_mensaje_usuario="sí")


def test_autorizar_borra_el_pendiente_y_exige_todo_de_nuevo_la_proxima_vez():
    autorizacion = Autorizacion()
    autorizacion.pedir(("x",), turno_actual=1, confirmado=False, ultimo_mensaje_usuario="")
    assert autorizacion.pedir(("x",), turno_actual=2, confirmado=True, ultimo_mensaje_usuario="sí")
    # una llamada posterior con la misma clave vuelve a empezar de cero
    assert not autorizacion.pedir(("x",), turno_actual=2, confirmado=True, ultimo_mensaje_usuario="sí")


def test_claves_distintas_no_se_interfieren():
    autorizacion = Autorizacion()
    autorizacion.pedir(("cerrar_aplicacion", "safari"), turno_actual=1, confirmado=False, ultimo_mensaje_usuario="")
    autorizacion.pedir(("recordar", "equipo", "boca"), turno_actual=1, confirmado=False, ultimo_mensaje_usuario="")
    # autorizar una clave no debe tocar el pendiente de la otra
    assert autorizacion.pedir(
        ("cerrar_aplicacion", "safari"), turno_actual=2, confirmado=True, ultimo_mensaje_usuario="sí"
    )
    assert autorizacion.pedir(
        ("recordar", "equipo", "boca"), turno_actual=2, confirmado=True, ultimo_mensaje_usuario="sí"
    )
