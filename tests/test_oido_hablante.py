"""Pruebas de Oido._coincide_con_dueño en aislamiento, sin cargar Whisper real
(que Oido.__init__ descarga/carga) ni SpeechBrain real: construye la
instancia sin pasar por __init__ (bypass deliberado) y mockea el verificador."""

from jarvis.voz.oido import Oido


def _oido_sin_init(**atributos) -> Oido:
    oido = Oido.__new__(Oido)
    oido.verificador = atributos.get("verificador")
    oido.referencia_voz = atributos.get("referencia_voz")
    return oido


class _VerificadorFalso:
    def __init__(self, coincide: bool):
        self._coincide = coincide

    def coincide(self, audio, referencia):
        return self._coincide


class _VerificadorQueFalla:
    def coincide(self, audio, referencia):
        raise RuntimeError("el modelo no cargó")


def test_sin_verificador_configurado_siempre_es_dueño():
    oido = _oido_sin_init(verificador=None, referencia_voz=None)
    assert oido._coincide_con_dueño(audio=object()) is True


def test_sin_referencia_enrolada_siempre_es_dueño():
    oido = _oido_sin_init(verificador=_VerificadorFalso(False), referencia_voz=None)
    assert oido._coincide_con_dueño(audio=object()) is True


def test_voz_coincide():
    oido = _oido_sin_init(verificador=_VerificadorFalso(True), referencia_voz=object())
    assert oido._coincide_con_dueño(audio=object()) is True


def test_voz_no_coincide():
    oido = _oido_sin_init(verificador=_VerificadorFalso(False), referencia_voz=object())
    assert oido._coincide_con_dueño(audio=object()) is False


def test_si_el_verificador_falla_falla_cerrado_no_abierto():
    """El audio lo controla quien habla: un error del verificador (p. ej. una
    grabación corrupta a propósito) no debe tratarse como "sí es el dueño" —
    sería una forma trivial de saltarse el gate de requiere_dueño."""
    oido = _oido_sin_init(verificador=_VerificadorQueFalla(), referencia_voz=object())
    assert oido._coincide_con_dueño(audio=object()) is False
