"""Pruebas de Config y de guardar_en_env (persistencia segura en .env)."""

from __future__ import annotations

import pytest

from jarvis.config import Config, guardar_en_env


def test_guardar_en_env_crea_archivo_con_permisos_0600(tmp_path):
    ruta = tmp_path / ".env"
    guardar_en_env("ANTHROPIC_API_KEY", "sk-ant-prueba", ruta)

    assert ruta.read_text() == "ANTHROPIC_API_KEY=sk-ant-prueba\n"
    assert (ruta.stat().st_mode & 0o777) == 0o600


def test_guardar_en_env_reemplaza_clave_existente_sin_tocar_el_resto(tmp_path):
    ruta = tmp_path / ".env"
    ruta.write_text("OTRA_CLAVE=no-tocar\nJARVIS_PROVEEDOR=anthropic\n")

    guardar_en_env("JARVIS_PROVEEDOR", "ollama", ruta)

    contenido = ruta.read_text().splitlines()
    assert "OTRA_CLAVE=no-tocar" in contenido
    assert "JARVIS_PROVEEDOR=ollama" in contenido
    assert "JARVIS_PROVEEDOR=anthropic" not in contenido


def test_guardar_en_env_agrega_clave_nueva_al_final(tmp_path):
    ruta = tmp_path / ".env"
    ruta.write_text("OTRA_CLAVE=valor\n")

    guardar_en_env("JARVIS_MODELO", "qwen3:8b", ruta)

    assert ruta.read_text() == "OTRA_CLAVE=valor\nJARVIS_MODELO=qwen3:8b\n"


def test_guardar_en_env_rechaza_salto_de_linea_en_el_valor(tmp_path):
    """Defensa en profundidad: no confía en que quien llama (p. ej. la
    herramienta "guardar_nombre", con un valor que decide el modelo) ya
    validó esto — un salto de línea en el valor inyectaría una línea nueva
    en .env, pisando cualquier otra variable."""
    ruta = tmp_path / ".env"
    with pytest.raises(ValueError):
        guardar_en_env("JARVIS_NOMBRE_USUARIO", "Pedro\nANTHROPIC_API_KEY=robada", ruta)
    assert not ruta.is_file()


def test_guardar_en_env_rechaza_salto_de_linea_en_la_clave(tmp_path):
    ruta = tmp_path / ".env"
    with pytest.raises(ValueError):
        guardar_en_env("CLAVE\nOTRA=x", "valor", ruta)
    assert not ruta.is_file()


def test_config_desde_entorno_lee_proveedor_y_url_de_ollama(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # sin .env real en el repo que interfiera
    monkeypatch.setenv("JARVIS_PROVEEDOR", "ollama")
    monkeypatch.setenv("JARVIS_MODELO", "qwen3:8b")
    monkeypatch.setenv("JARVIS_OLLAMA_URL", "http://localhost:9999")

    config = Config.desde_entorno()

    assert config.proveedor == "ollama"
    assert config.modelo == "qwen3:8b"
    assert config.ollama_url == "http://localhost:9999"


def test_config_proveedor_por_defecto_es_anthropic():
    assert Config().proveedor == "anthropic"
