"""
Instalador gráfico de Jarvis: wizard paso a paso.

Orden fijo, sin saltos: Términos y Condiciones -> instalar Ollama (bloquea
si el usuario rehúsa) -> escaneo de hardware (solo después de aceptar los
términos) -> selección de modelo -> resto de la instalación -> abrir Jarvis
o cerrar. Cada pantalla vive en su propio módulo bajo ``pantallas/`` y solo
conoce sus propios callbacks (``al_aceptar``, etc.) — este archivo es el
único que sabe en qué orden van.
"""

import toga

from .pantallas.ollama import PantallaOllama
from .pantallas.terminos import PantallaTerminos


class InstaladordeJarvis(toga.App):
    def startup(self):
        self.main_window = toga.MainWindow(title=self.formal_name, size=(640, 560))
        self._mostrar_terminos()
        self.main_window.show()

    def _mostrar_terminos(self) -> None:
        pantalla = PantallaTerminos(
            al_aceptar=self._terminos_aceptados,
            al_rechazar=self._terminos_rechazados,
        )
        self.main_window.content = pantalla.contenido

    def _terminos_aceptados(self) -> None:
        self._mostrar_ollama()

    def _mostrar_ollama(self) -> None:
        pantalla = PantallaOllama(al_continuar=self._ollama_listo)
        self.main_window.content = pantalla.contenido

    def _ollama_listo(self) -> None:
        # Próximo paso (escaneo de hardware) se agrega en el siguiente incremento.
        self.main_window.content = toga.Box()

    def _terminos_rechazados(self) -> None:
        self.exit()


def main():
    return InstaladordeJarvis()
