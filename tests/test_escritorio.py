"""Pruebas del lanzador de escritorio: generan archivos reales bajo tmp_path,
nunca tocan ~/Applications ni el menú de aplicaciones real."""

from pathlib import Path

from jarvis.escritorio import instalar_app_escritorio


def test_macos_crea_app_bundle_ejecutable(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "darwin")
    python = Path("/usr/bin/python3")

    app = instalar_app_escritorio(python=python, home=tmp_path)

    assert app == tmp_path / "Applications" / "Jarvis.app"
    lanzador = app / "Contents" / "MacOS" / "jarvis"
    contenido = lanzador.read_text()
    assert str(python) in contenido
    assert "-m jarvis" in contenido
    assert str(tmp_path / ".jarvis" / "jarvis.log") in contenido
    assert lanzador.stat().st_mode & 0o100  # ejecutable para el dueño
    assert "CFBundleExecutable" in (app / "Contents" / "Info.plist").read_text()


def test_windows_crea_bat_sin_consola(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "win32")
    python = Path("C:/Python312/python.exe")

    lanzador = instalar_app_escritorio(python=python, home=tmp_path)

    assert lanzador.name == "Jarvis.bat"
    contenido = lanzador.read_text()
    assert "pythonw.exe" in contenido  # sin ventana de consola
    assert "-m jarvis" in contenido


def test_linux_crea_entrada_desktop_sin_terminal(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    python = Path("/usr/bin/python3")

    entrada = instalar_app_escritorio(python=python, home=tmp_path)

    assert entrada == tmp_path / ".local" / "share" / "applications" / "jarvis.desktop"
    contenido = entrada.read_text()
    assert "Terminal=false" in contenido
    assert "-m jarvis" in contenido
    assert entrada.stat().st_mode & 0o100


def test_usa_sys_executable_por_defecto(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("sys.executable", "/opt/venv/bin/python3")

    entrada = instalar_app_escritorio(home=tmp_path)

    assert "/opt/venv/bin/python3" in entrada.read_text()
