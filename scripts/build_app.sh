#!/bin/bash
# Construye el bundle standalone de Jarvis con PyInstaller (modo --onedir)
# a partir de jarvis.spec. Pensado para macOS y Linux (en Windows, el
# workflow de CI llama a pyinstaller directamente desde PowerShell: ver
# .github/workflows/build-app.yml).
#
# Uso:
#   scripts/build_app.sh
#
# Requiere: el venv de desarrollo con el grupo opcional "build" instalado:
#   pip install -e ".[build]"
#
# Salida:
#   - macOS:  dist/Jarvis.app
#   - Linux:  dist/jarvis/ (carpeta con el binario "jarvis" adentro)
# Autocontenido en ambos casos: no depende de este repo ni de este venv
# para arrancar. Los modelos de voz (Whisper, Kokoro, Piper) NO se incluyen
# en el bundle: se siguen descargando a ~/.jarvis o a la caché de
# huggingface en el primer uso real, igual que corriendo desde el repo.
#
# El primer build tarda varios minutos (torch + transformers son pesados).
# Builds siguientes son más rápidos porque PyInstaller cachea el análisis.

set -euo pipefail
cd "$(dirname "$0")/.."

if ! python -c "import PyInstaller" 2>/dev/null; then
    echo "Falta PyInstaller en este entorno. Instalalo con:"
    echo "  pip install -e \".[build]\""
    exit 1
fi

rm -rf build dist

echo "Construyendo Jarvis con PyInstaller (esto puede tardar varios minutos)..."
pyinstaller --noconfirm --clean jarvis.spec

if [ -d "dist/Jarvis.app" ]; then
    SALIDA="dist/Jarvis.app"
elif [ -d "dist/jarvis" ]; then
    SALIDA="dist/jarvis"
else
    echo "El build terminó pero no encuentro dist/Jarvis.app ni dist/jarvis." >&2
    exit 1
fi

echo
echo "Listo: $SALIDA"
du -sh "$SALIDA"
