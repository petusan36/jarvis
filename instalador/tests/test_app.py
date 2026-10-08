"""Pruebas de app.py: el controlador del wizard (orden de pantallas)."""

from instalador.app import InstaladordeJarvis


def test_app_se_puede_instanciar():
    """Smoke test: la app arranca sin reventar — más que esto no se puede
    probar sin el ciclo de vida real de startup()/main_window, que exige
    un backend gráfico real (ver briefcase dev, probado a mano)."""
    app = InstaladordeJarvis(formal_name="Instalador de Jarvis", app_id="com.jarvis.instalador")
    assert app is not None
