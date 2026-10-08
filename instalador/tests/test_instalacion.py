"""Pruebas de descarga e instalación del bundle real de Jarvis (ver
src/instalador/instalacion.py), sin UI. Las llamadas de red (API de
releases, descarga del zip) se mockean siempre — un test no debe depender
de GitHub ni de que haya un release publicado."""

import json
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from instalador import instalacion


def _release_falso(assets):
    return json.dumps({"assets": assets}).encode()


def test_obtener_url_bundle_macos(monkeypatch):
    monkeypatch.setattr(instalacion.sys, "platform", "darwin")
    respuesta_falsa = MagicMock()
    respuesta_falsa.read.return_value = _release_falso([
        {"name": "jarvis-macos.zip", "browser_download_url": "https://example.com/jarvis-macos.zip"},
        {"name": "jarvis-windows.zip", "browser_download_url": "https://example.com/jarvis-windows.zip"},
    ])
    respuesta_falsa.__enter__.return_value = respuesta_falsa
    with patch.object(instalacion.urllib.request, "urlopen", return_value=respuesta_falsa) as urlopen_falso:
        url = instalacion.obtener_url_bundle()

    assert urlopen_falso.call_args[0][0] == instalacion.URL_RELEASES_LATEST
    assert url == "https://example.com/jarvis-macos.zip"


def test_obtener_url_bundle_sin_release_publicado_levanta_error():
    with patch.object(instalacion.urllib.request, "urlopen", side_effect=instalacion.urllib.error.URLError("404")):
        with pytest.raises(instalacion.ErrorInstalacionJarvis, match="No se pudo consultar"):
            instalacion.obtener_url_bundle()


def test_obtener_url_bundle_sin_asset_para_este_so_levanta_error(monkeypatch):
    monkeypatch.setattr(instalacion.sys, "platform", "linux")
    respuesta_falsa = MagicMock()
    respuesta_falsa.read.return_value = _release_falso([
        {"name": "jarvis-macos.zip", "browser_download_url": "https://example.com/jarvis-macos.zip"},
    ])
    respuesta_falsa.__enter__.return_value = respuesta_falsa
    with patch.object(instalacion.urllib.request, "urlopen", return_value=respuesta_falsa):
        with pytest.raises(instalacion.ErrorInstalacionJarvis, match="jarvis-linux.zip"):
            instalacion.obtener_url_bundle()


def test_so_no_soportado_levanta_error(monkeypatch):
    monkeypatch.setattr(instalacion.sys, "platform", "freebsd13")
    with pytest.raises(instalacion.ErrorInstalacionJarvis, match="no soportado"):
        instalacion._zip_para_esta_plataforma()


def test_encontrar_bundle_con_un_solo_elemento_en_la_raiz(tmp_path):
    carpeta_app = tmp_path / "Jarvis.app"
    carpeta_app.mkdir()
    assert instalacion._encontrar_bundle(tmp_path) == carpeta_app


def test_encontrar_bundle_con_forma_inesperada_levanta_error(tmp_path):
    (tmp_path / "uno").mkdir()
    (tmp_path / "dos").mkdir()
    with pytest.raises(instalacion.ErrorInstalacionJarvis, match="forma esperada"):
        instalacion._encontrar_bundle(tmp_path)


def test_instalar_macos_copia_el_app_a_applications(tmp_path):
    origen = tmp_path / "origen" / "Jarvis.app"
    (origen / "Contents").mkdir(parents=True)
    (origen / "Contents" / "marca").write_text("real")
    home = tmp_path / "home"

    resultado = instalacion._instalar_macos(origen, home)

    assert resultado == home / "Applications" / "Jarvis.app"
    assert (resultado / "Contents" / "marca").read_text() == "real"


def test_instalar_macos_reemplaza_instalacion_anterior(tmp_path):
    origen = tmp_path / "origen" / "Jarvis.app"
    origen.mkdir(parents=True)
    (origen / "nuevo").write_text("v2")
    home = tmp_path / "home"
    destino_viejo = home / "Applications" / "Jarvis.app"
    destino_viejo.mkdir(parents=True)
    (destino_viejo / "viejo").write_text("v1")

    instalacion._instalar_macos(origen, home)

    assert not (destino_viejo / "viejo").exists()
    assert (destino_viejo / "nuevo").read_text() == "v2"


def test_instalar_linux_crea_entrada_de_escritorio(tmp_path):
    origen = tmp_path / "origen" / "jarvis"
    origen.mkdir(parents=True)
    (origen / "jarvis").write_text("binario falso")
    home = tmp_path / "home"

    entrada = instalacion._instalar_linux(origen, home)

    assert entrada.is_file()
    contenido = entrada.read_text()
    assert "Exec=" in contenido
    assert str(home / ".local" / "share" / "jarvis" / "app" / "jarvis") in contenido


def test_instalar_windows_crea_lanzador_bat(tmp_path):
    origen = tmp_path / "origen" / "jarvis"
    origen.mkdir(parents=True)
    (origen / "jarvis.exe").write_text("binario falso")
    home = tmp_path / "home"

    lanzador = instalacion._instalar_windows(origen, home)

    assert lanzador.name == "Jarvis.bat"
    assert "jarvis.exe" in lanzador.read_text()


def test_descargar_e_instalar_flujo_completo_con_red_mockeada(tmp_path, monkeypatch):
    """De punta a punta, pero sin tocar la red real: arma un zip real en
    disco (igual forma que el que publicaría el workflow de release) y
    verifica que termine instalado en el lugar correcto."""
    monkeypatch.setattr(instalacion.sys, "platform", "darwin")
    home = tmp_path / "home"

    zip_fuente = tmp_path / "jarvis-macos.zip"
    with zipfile.ZipFile(zip_fuente, "w") as z:
        z.writestr("Jarvis.app/Contents/marca", "real")

    respuesta_falsa = MagicMock()
    respuesta_falsa.read.return_value = _release_falso([
        {"name": "jarvis-macos.zip", "browser_download_url": "https://example.com/jarvis-macos.zip"},
    ])
    respuesta_falsa.__enter__.return_value = respuesta_falsa

    def urlretrieve_falso(url, destino):
        import shutil
        shutil.copy(zip_fuente, destino)

    progreso = []
    with patch.object(instalacion.urllib.request, "urlopen", return_value=respuesta_falsa):
        with patch.object(instalacion.urllib.request, "urlretrieve", side_effect=urlretrieve_falso):
            resultado = instalacion.descargar_e_instalar(reportar=progreso.append, home=home)

    assert resultado == home / "Applications" / "Jarvis.app"
    assert (resultado / "Contents" / "marca").read_text() == "real"
    assert any("Descargando" in linea for linea in progreso)
    assert any("Extrayendo" in linea for linea in progreso)
    assert "Listo." in progreso


def test_abrir_jarvis_en_macos_usa_open(monkeypatch, tmp_path):
    monkeypatch.setattr(instalacion.sys, "platform", "darwin")
    ruta = tmp_path / "Jarvis.app"
    with patch.object(instalacion.subprocess, "Popen") as popen_falso:
        instalacion.abrir_jarvis(ruta)
    assert popen_falso.call_args[0][0] == ["open", str(ruta)]


def test_abrir_jarvis_en_windows_usa_os_startfile(monkeypatch, tmp_path):
    monkeypatch.setattr(instalacion.sys, "platform", "win32")
    ruta = tmp_path / "Jarvis.bat"
    with patch.object(instalacion.os, "startfile", create=True) as startfile_falso:
        instalacion.abrir_jarvis(ruta)
    startfile_falso.assert_called_once_with(str(ruta))


def test_abrir_jarvis_en_linux_usa_gio_launch(monkeypatch, tmp_path):
    monkeypatch.setattr(instalacion.sys, "platform", "linux")
    ruta = tmp_path / "jarvis.desktop"
    with patch.object(instalacion.subprocess, "Popen") as popen_falso:
        instalacion.abrir_jarvis(ruta)
    assert popen_falso.call_args[0][0] == ["gio", "launch", str(ruta)]


def test_abrir_jarvis_si_falla_no_levanta_excepcion(monkeypatch, tmp_path):
    """El usuario igual tiene el acceso directo instalado para abrirlo a
    mano — no vale la pena romper el último paso del wizard por esto."""
    monkeypatch.setattr(instalacion.sys, "platform", "darwin")
    with patch.object(instalacion.subprocess, "Popen", side_effect=OSError("no encontrado")):
        instalacion.abrir_jarvis(tmp_path / "Jarvis.app")  # no debe lanzar
