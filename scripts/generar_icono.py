"""Genera el ícono de la app (assets/jarvis_icono.png, 1024x1024) con el
mismo esquema visual del HUD ("Ojo de Dios" / Southern Ring Nebula, ver
jarvis/hud/hud.html): anillo de polvo ámbar/brasa, núcleo azul-blanco frío,
estrella central con picos de difracción.

Uso:
    python scripts/generar_icono.py

Después, en macOS, compilar a .icns:
    mkdir -p assets/jarvis.iconset
    for s in 16 32 128 256 512; do
        sips -z $s $s assets/jarvis_icono.png --out assets/jarvis.iconset/icon_${s}x${s}.png
        sips -z $((s*2)) $((s*2)) assets/jarvis_icono.png --out assets/jarvis.iconset/icon_${s}x${s}@2x.png
    done
    cp assets/jarvis_icono.png assets/jarvis.iconset/icon_512x512@2x.png
    iconutil -c icns assets/jarvis.iconset -o assets/jarvis.icns

Requiere Pillow (ya es dependencia del proyecto vía el extra de voz/imagen).
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

TAMANO = 1024
CENTRO = TAMANO / 2

TONO_ANILLO_ORO = (255, 196, 120)
TONO_ANILLO_BRASA = (120, 56, 28)
TONO_NUCLEO_FRIO = (150, 205, 255)
TONO_ESTRELLA = (120, 230, 255)  # tono "hablando" del HUD: el más vistoso para un ícono estático
FONDO = (3, 6, 12)


def _mezclar(a: tuple[int, int, int], b: tuple[int, int, int], f: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * f) for i in range(3))


def _blob(dibujo: ImageDraw.ImageDraw, x: float, y: float, radio: float, color: tuple[int, int, int], alfa: int) -> None:
    dibujo.ellipse([x - radio, y - radio, x + radio, y + radio], fill=(*color, alfa))


def generar() -> Image.Image:
    random.seed(7)  # reproducible: mismo ícono en cada build, no cambia solo
    base = Image.new("RGBA", (TAMANO, TAMANO), (*FONDO, 255))

    capa_nucleo = Image.new("RGBA", (TAMANO, TAMANO), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa_nucleo)
    for radio, alfa in [(340, 70), (260, 110), (180, 160), (110, 210)]:
        _blob(d, CENTRO, CENTRO, radio, TONO_NUCLEO_FRIO, alfa)
    capa_nucleo = capa_nucleo.filter(ImageFilter.GaussianBlur(18))
    base = Image.alpha_composite(base, capa_nucleo)

    capa_anillo = Image.new("RGBA", (TAMANO, TAMANO), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa_anillo)
    n_jirones = 90
    for i in range(n_jirones):
        angulo = (i / n_jirones) * math.pi * 2 + random.uniform(-0.05, 0.05)
        radio_base = random.uniform(0.52, 0.92)
        f = (radio_base - 0.52) / 0.40
        color = _mezclar(TONO_ANILLO_ORO, TONO_ANILLO_BRASA, f)
        radio_jiron = radio_base * TAMANO * 0.46
        x = CENTRO + math.cos(angulo) * radio_jiron
        y = CENTRO + math.sin(angulo) * radio_jiron
        tamano_blob = random.uniform(55, 110)
        _blob(d, x, y, tamano_blob, color, random.randint(140, 220))
    capa_anillo = capa_anillo.filter(ImageFilter.GaussianBlur(10))
    base = Image.alpha_composite(base, capa_anillo)

    capa_estrellas = Image.new("RGBA", (TAMANO, TAMANO), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa_estrellas)
    for _ in range(26):
        radio_base = random.uniform(0.15, 1.35)
        angulo = random.uniform(0, math.pi * 2)
        radio_punto = radio_base * TAMANO * 0.46
        x = CENTRO + math.cos(angulo) * radio_punto
        y = CENTRO + math.sin(angulo) * radio_punto
        if not (0 <= x <= TAMANO and 0 <= y <= TAMANO):
            continue
        r = random.uniform(2, 6)
        alfa = random.randint(120, 255)
        _blob(d, x, y, r, (255, 255, 255), alfa)
    base = Image.alpha_composite(base, capa_estrellas)

    # Estrella central con picos de difracción, igual que el HUD en vivo.
    capa_central = Image.new("RGBA", (TAMANO, TAMANO), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa_central)
    largo_mayor, largo_menor = 300, 130
    d.line([CENTRO - largo_mayor, CENTRO, CENTRO + largo_mayor, CENTRO], fill=(*TONO_ESTRELLA, 220), width=5)
    d.line([CENTRO, CENTRO - largo_mayor, CENTRO, CENTRO + largo_mayor], fill=(*TONO_ESTRELLA, 220), width=5)
    diag = largo_menor / math.sqrt(2)
    d.line([CENTRO - diag, CENTRO - diag, CENTRO + diag, CENTRO + diag], fill=(*TONO_ESTRELLA, 150), width=3)
    d.line([CENTRO - diag, CENTRO + diag, CENTRO + diag, CENTRO - diag], fill=(*TONO_ESTRELLA, 150), width=3)
    capa_central = capa_central.filter(ImageFilter.GaussianBlur(2))
    base = Image.alpha_composite(base, capa_central)

    capa_nucleo_brillo = Image.new("RGBA", (TAMANO, TAMANO), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa_nucleo_brillo)
    _blob(d, CENTRO, CENTRO, 55, (255, 255, 255), 255)
    _blob(d, CENTRO, CENTRO, 90, TONO_ESTRELLA, 180)
    capa_nucleo_brillo = capa_nucleo_brillo.filter(ImageFilter.GaussianBlur(6))
    base = Image.alpha_composite(base, capa_nucleo_brillo)

    return base.convert("RGB")


if __name__ == "__main__":
    salida = Path(__file__).resolve().parent.parent / "assets" / "jarvis_icono.png"
    salida.parent.mkdir(parents=True, exist_ok=True)
    generar().save(salida)
    print(f"Listo: {salida}")
