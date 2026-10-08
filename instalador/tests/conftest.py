"""El backend dummy de Toga (``toga_dummy``) permite instanciar widgets y
ventanas sin un entorno gráfico real — mismo backend que usa el propio
proyecto Toga para sus tests. Tiene que fijarse ANTES de que cualquier
módulo importe ``toga``, por eso vive acá y no en cada archivo de test."""

import os
import sys
from pathlib import Path

os.environ.setdefault("TOGA_BACKEND", "toga_dummy")
# El proyecto no se instala (Briefcase no usa setuptools/pip install -e para
# esto): agregar src/ al path alcanza para importar el paquete en los tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
