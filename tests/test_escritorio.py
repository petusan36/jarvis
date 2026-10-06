"""Pruebas del lanzador de escritorio: generan archivos reales bajo tmp_path,
nunca tocan ~/Applications ni el menú de aplicaciones real.

`instalar_app_escritorio` ya no crea un lanzador fino que invoca
`{python} -m jarvis`: copia el bundle standalone construido con PyInstaller
(`dist/Jarvis.app` en macOS, `dist/jarvis/` en Windows/Linux). Estas pruebas
simulan ese bundle ya construido bajo un `repo_raiz` falso."""

from pathlib import Path

import pytest

from jarvis.escritorio import MENSAJE_FALTA_BUILD, instalar_app_escritorio


def _crear_bundle_macos(repo_raiz: Path) -> Path:
    app = repo_raiz / "dist" / "Jarvis.app" / "Contents" / "MacOS"
    app.mkdir(parents=True)
    (app / "jarvis").write_text("#!/bin/sh\necho binario standalone\n")
    return repo_raiz / "dist" / "Jarvis.app"


def _crear_bundle_onedir(repo_raiz: Path, ejecutable: str) -> Path:
    carpeta = repo_raiz / "dist" / "jarvis"
    carpeta.mkdir(parents=True)
    (carpeta / ejecutable).write_text("binario standalone")
    return carpeta


def test_macos_copia_el_app_bundle_ya_construido(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "darwin")
    repo_raiz = tmp_path / "repo"
    home = tmp_path / "home"
    _crear_bundle_macos(repo_raiz)

    app = instalar_app_escritorio(home=home, repo_raiz=repo_raiz)

    assert app == home / "Applications" / "Jarvis.app"
    assert (app / "Contents" / "MacOS" / "jarvis").is_file()


def test_macos_sin_build_previo_lanza_error_claro(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "darwin")
    repo_raiz = tmp_path / "repo"  # sin dist/Jarvis.app
    home = tmp_path / "home"

    with pytest.raises(RuntimeError) as excinfo:
        instalar_app_escritorio(home=home, repo_raiz=repo_raiz)

    assert "scripts/build_app.sh" in str(excinfo.value)
    assert MENSAJE_FALTA_BUILD.split("{")[0] in str(excinfo.value)


def test_windows_copia_el_onedir_y_crea_lanzador_bat(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "win32")
    repo_raiz = tmp_path / "repo"
    home = tmp_path / "home"
    _crear_bundle_onedir(repo_raiz, "jarvis.exe")

    lanzador = instalar_app_escritorio(home=home, repo_raiz=repo_raiz)

    assert lanzador.name == "Jarvis.bat"
    contenido = lanzador.read_text()
    assert "jarvis.exe" in contenido
    assert "python" not in contenido.lower()  # standalone: no invoca ningún Python
    carpeta_app = home / "AppData" / "Local" / "Jarvis" / "app"
    assert (carpeta_app / "jarvis.exe").is_file()


def test_windows_sin_build_previo_lanza_error_claro(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "win32")
    repo_raiz = tmp_path / "repo"
    home = tmp_path / "home"

    with pytest.raises(RuntimeError, match="scripts/build_app.sh"):
        instalar_app_escritorio(home=home, repo_raiz=repo_raiz)


def test_linux_copia_el_onedir_y_crea_entrada_desktop(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    repo_raiz = tmp_path / "repo"
    home = tmp_path / "home"
    _crear_bundle_onedir(repo_raiz, "jarvis")

    entrada = instalar_app_escritorio(home=home, repo_raiz=repo_raiz)

    assert entrada == home / ".local" / "share" / "applications" / "jarvis.desktop"
    contenido = entrada.read_text()
    assert "Terminal=false" in contenido
    carpeta_app = home / ".local" / "share" / "jarvis" / "app"
    assert str(carpeta_app / "jarvis") in contenido
    assert entrada.stat().st_mode & 0o100
    assert (carpeta_app / "jarvis").is_file()


def test_linux_sin_build_previo_lanza_error_claro(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    repo_raiz = tmp_path / "repo"
    home = tmp_path / "home"

    with pytest.raises(RuntimeError, match="scripts/build_app.sh"):
        instalar_app_escritorio(home=home, repo_raiz=repo_raiz)


def test_reinstalar_reemplaza_el_bundle_anterior(monkeypatch, tmp_path):
    """Instalar dos veces no debe fallar ni dejar restos del bundle viejo."""
    monkeypatch.setattr("sys.platform", "darwin")
    repo_raiz = tmp_path / "repo"
    home = tmp_path / "home"
    _crear_bundle_macos(repo_raiz)
    instalar_app_escritorio(home=home, repo_raiz=repo_raiz)

    # Bundle viejo instalado con un archivo que ya no existe en el nuevo build.
    viejo = home / "Applications" / "Jarvis.app" / "Contents" / "MacOS" / "archivo_viejo"
    viejo.write_text("restos de una versión anterior")

    instalar_app_escritorio(home=home, repo_raiz=repo_raiz)

    assert not viejo.exists()
