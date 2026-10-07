"""Pruebas del modo de escucha pasiva de Oido (ver jarvis.herramientas
"dormir_jarvis"), sin cargar Whisper real: construye la instancia sin pasar
por __init__ (mismo bypass que test_oido_hablante.py) y mockea la grabación
y la transcripción para ejercitar escuchar() de punta a punta."""

import time

from jarvis.hud import HudNulo
from jarvis.voz.oido import Oido


def _oido_reposo(segundos_reposo_inactividad=0.0, al_dormir=None, al_despertar=None,
                 palabra_activacion=""):
    oido = Oido.__new__(Oido)
    oido.hud = HudNulo()
    oido.pulsar = False
    oido.palabra_activacion = palabra_activacion
    oido.verificador = None
    oido.referencia_voz = None
    oido.es_dueño = True
    oido.en_reposo = False
    oido.segundos_reposo_inactividad = segundos_reposo_inactividad
    oido.al_dormir = al_dormir or (lambda: None)
    oido.al_despertar = al_despertar or (lambda: None)
    oido._temporizador_reposo = None
    return oido


def _con_frase(oido, texto: str):
    """Hace que la próxima vuelta de escuchar() devuelva ``texto`` transcrito,
    sin grabar ni transcribir audio real."""
    oido._grabar_continuo = lambda: object()
    oido._transcribir = lambda _audio: texto


# --- dormir() / _despertar() en aislamiento ---------------------------------

def test_dormir_activa_reposo_y_llama_al_dormir():
    llamadas = []
    oido = _oido_reposo(al_dormir=lambda: llamadas.append("dormir"))
    oido.dormir()
    assert oido.en_reposo is True
    assert llamadas == ["dormir"]


def test_dormir_es_idempotente_no_llama_dos_veces():
    llamadas = []
    oido = _oido_reposo(al_dormir=lambda: llamadas.append("dormir"))
    oido.dormir()
    oido.dormir()
    assert llamadas == ["dormir"]  # la segunda llamada no vuelve a disparar el gancho


def test_despertar_desactiva_reposo_y_llama_al_despertar():
    llamadas = []
    oido = _oido_reposo(al_despertar=lambda: llamadas.append("despertar"))
    oido.en_reposo = True
    oido._despertar()
    assert oido.en_reposo is False
    assert llamadas == ["despertar"]


# --- escuchar(): en reposo exige el nombre aunque no haya palabra_activacion ---

def test_en_reposo_ignora_frases_sin_nombrarlo():
    oido = _oido_reposo()
    oido.en_reposo = True
    _con_frase(oido, "qué hora es")
    # nunca nombra a Jarvis: escuchar() seguiría esperando para siempre en la
    # vida real (bucle infinito de _grabar_continuo); para no colgar el test,
    # verificamos la decisión de UNA vuelta directamente.
    from jarvis.voz.oido import PALABRA_DESPERTAR, filtrar_palabra_activacion
    palabra = oido.palabra_activacion or (PALABRA_DESPERTAR if oido.en_reposo else "")
    assert filtrar_palabra_activacion("qué hora es", palabra) == ""


def test_en_reposo_nombrarlo_despierta_y_devuelve_el_resto():
    oido = _oido_reposo()
    oido.en_reposo = True
    _con_frase(oido, "Jarvis, qué hora es")

    assert oido.escuchar() == "qué hora es"
    assert oido.en_reposo is False


def test_nombrarlo_en_reposo_llama_al_despertar():
    llamadas = []
    oido = _oido_reposo(al_despertar=lambda: llamadas.append("despertar"))
    oido.en_reposo = True
    _con_frase(oido, "Jarvis, qué hora es")

    oido.escuchar()
    assert llamadas == ["despertar"]


def test_sin_reposo_no_exige_nombrarlo_aunque_no_haya_palabra_activacion():
    oido = _oido_reposo()  # en_reposo=False, palabra_activacion=""
    _con_frase(oido, "qué hora es")
    assert oido.escuchar() == "qué hora es"


def test_palabra_activacion_configurada_sigue_exigiendose_sin_reposo():
    """El modo reposo no reemplaza palabra_activacion si ya estaba puesta:
    solo agrega la exigencia cuando no había ninguna."""
    oido = _oido_reposo(palabra_activacion="oye")
    frases = iter(["qué hora es", "oye, qué hora es"])  # la primera no la nombra: se ignora

    oido._grabar_continuo = lambda: object()
    oido._transcribir = lambda _audio: next(frases)

    assert oido.escuchar() == "qué hora es"


# --- temporizador de inactividad real (threading.Timer, tiempo real corto) ---

def test_temporizador_de_inactividad_duerme_solo_tras_el_timeout():
    oido = _oido_reposo(segundos_reposo_inactividad=0.05)
    oido._reiniciar_temporizador_reposo()
    assert oido.en_reposo is False
    time.sleep(0.2)
    assert oido.en_reposo is True


def test_reiniciar_temporizador_antes_del_timeout_lo_posterga():
    oido = _oido_reposo(segundos_reposo_inactividad=0.1)
    oido._reiniciar_temporizador_reposo()
    time.sleep(0.05)
    oido._reiniciar_temporizador_reposo()  # "actividad" a mitad de camino: reinicia la cuenta
    time.sleep(0.07)
    assert oido.en_reposo is False  # todavía no pasaron los 0.1s desde el reinicio
    time.sleep(0.08)
    assert oido.en_reposo is True


def test_timeout_cero_desactiva_el_reposo_automatico():
    oido = _oido_reposo(segundos_reposo_inactividad=0.0)
    oido._reiniciar_temporizador_reposo()
    time.sleep(0.1)
    assert oido.en_reposo is False  # nunca se arma el temporizador
