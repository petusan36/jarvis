"""Punto de entrada para PyInstaller: equivalente a `python -m jarvis`.

PyInstaller necesita un script concreto como `Analysis(["..."])`, no un
`-m`; este archivo solo reexporta `jarvis.__main__.main` para que el
análisis estático descubra el mismo grafo de imports que usa el CLI real.
"""

from __future__ import annotations

import sys

from jarvis.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
