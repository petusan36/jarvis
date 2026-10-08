"""Pruebas del escaneo de hardware (ver src/instalador/hardware.py), sin UI."""

import subprocess
from unittest.mock import MagicMock, patch

from instalador import hardware


def test_escanear_hardware_usa_cpu_count_y_psutil(monkeypatch):
    monkeypatch.setattr(hardware.os, "cpu_count", lambda: 8)
    memoria_falsa = MagicMock(total=17179869184)  # 16 GiB exactos
    with patch("psutil.virtual_memory", return_value=memoria_falsa):
        with patch.object(hardware, "_detectar_gpu", return_value="GPU de prueba"):
            info = hardware.escanear_hardware()

    assert info.nucleos_cpu == 8
    assert info.ram_total_gb == 16.0
    assert info.gpu_nombre == "GPU de prueba"


def test_sin_cpu_count_usa_1_como_piso(monkeypatch):
    monkeypatch.setattr(hardware.os, "cpu_count", lambda: None)
    memoria_falsa = MagicMock(total=8589934592)
    with patch("psutil.virtual_memory", return_value=memoria_falsa):
        with patch.object(hardware, "_detectar_gpu", return_value=None):
            info = hardware.escanear_hardware()
    assert info.nucleos_cpu == 1


def test_detectar_gpu_macos_lee_el_json_real_de_system_profiler(monkeypatch):
    salida_falsa = MagicMock(
        stdout='{"SPDisplaysDataType": [{"_name": "Apple M2 Pro"}]}'
    )
    with patch.object(hardware.subprocess, "run", return_value=salida_falsa):
        assert hardware._detectar_gpu_macos() == "Apple M2 Pro"


def test_detectar_gpu_macos_sin_pantallas_devuelve_none():
    salida_falsa = MagicMock(stdout='{"SPDisplaysDataType": []}')
    with patch.object(hardware.subprocess, "run", return_value=salida_falsa):
        assert hardware._detectar_gpu_macos() is None


def test_detectar_gpu_macos_si_el_comando_falla_devuelve_none():
    with patch.object(hardware.subprocess, "run", side_effect=subprocess.SubprocessError):
        assert hardware._detectar_gpu_macos() is None


def test_detectar_gpu_linux_prefiere_nvidia_smi():
    salida_nvidia = MagicMock(stdout="NVIDIA GeForce RTX 4090\n")
    with patch.object(hardware.subprocess, "run", return_value=salida_nvidia):
        assert hardware._detectar_gpu_linux() == "NVIDIA GeForce RTX 4090"


def test_detectar_gpu_linux_cae_a_lspci_sin_nvidia():
    salida_lspci = MagicMock(stdout="01:00.0 VGA compatible controller: Intel UHD Graphics\n")

    def run_falso(comando, **_kw):
        if comando[0] == "nvidia-smi":
            raise FileNotFoundError
        return salida_lspci

    with patch.object(hardware.subprocess, "run", side_effect=run_falso):
        assert "Intel UHD Graphics" in hardware._detectar_gpu_linux()


def test_detectar_gpu_devuelve_none_si_nada_funciona():
    with patch.object(hardware.subprocess, "run", side_effect=OSError):
        assert hardware._detectar_gpu_linux() is None
        assert hardware._detectar_gpu_windows() is None


def test_detectar_gpu_despacha_segun_plataforma(monkeypatch):
    monkeypatch.setattr(hardware.sys, "platform", "darwin")
    with patch.object(hardware, "_detectar_gpu_macos", return_value="mac") as m:
        assert hardware._detectar_gpu() == "mac"
        m.assert_called_once()

    monkeypatch.setattr(hardware.sys, "platform", "win32")
    with patch.object(hardware, "_detectar_gpu_windows", return_value="win") as w:
        assert hardware._detectar_gpu() == "win"
        w.assert_called_once()
