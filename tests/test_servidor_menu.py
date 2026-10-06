"""Pruebas del servidor HTTP del menú en ventana: estado, polling y acciones.

Usa el servidor real (HTTP local en 127.0.0.1, puerto efímero) porque es
liviano y rápido — lo que NO se prueba acá es la ventana nativa en sí
(necesita sesión gráfica real), solo el backend que la alimenta.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from jarvis.hud.servidor_menu import ServidorMenu


def _get(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, resp.read()


def _post(url: str, cuerpo: dict, token: str | None = None) -> int:
    datos = json.dumps(cuerpo).encode("utf-8")
    headers = {"X-Jarvis-Token": token} if token is not None else {}
    peticion = urllib.request.Request(url, data=datos, method="POST", headers=headers)
    with urllib.request.urlopen(peticion, timeout=5) as resp:
        return resp.status


def test_estado_inicial_es_inicio():
    servidor = ServidorMenu()
    try:
        assert servidor.estado() == {"paso": "inicio"}
    finally:
        servidor.cerrar()


def test_actualizar_reemplaza_el_estado_completo():
    servidor = ServidorMenu()
    try:
        servidor.actualizar(paso="local", modelos=["qwen3:8b"])
        assert servidor.estado() == {"paso": "local", "modelos": ["qwen3:8b"]}
        servidor.actualizar(paso="proveedor")  # sin "modelos": no debe quedar pegado
        assert servidor.estado() == {"paso": "proveedor"}
    finally:
        servidor.cerrar()


def test_pagina_principal_sirve_html():
    servidor = ServidorMenu()
    try:
        codigo, cuerpo = _get(servidor.url)
        assert codigo == 200
        assert b"<html" in cuerpo.lower()
    finally:
        servidor.cerrar()


def test_get_estado_devuelve_json_del_estado_actual():
    servidor = ServidorMenu()
    try:
        servidor.actualizar(paso="hecho", mensaje="listo")
        codigo, cuerpo = _get(servidor.url + "estado")
        assert codigo == 200
        assert json.loads(cuerpo) == {"paso": "hecho", "mensaje": "listo"}
    finally:
        servidor.cerrar()


def test_post_accion_llega_a_esperar_accion():
    servidor = ServidorMenu()
    try:
        codigo = _post(servidor.url + "accion", {"tipo": "local"}, token=servidor.token)
        assert codigo == 204
        assert servidor.esperar_accion(timeout=5) == {"tipo": "local"}
    finally:
        servidor.cerrar()


def test_post_accion_sin_token_da_403_y_no_llega_a_esperar_accion():
    """CSRF: una página de otro origen que le pegue a /accion sin conocer el
    token (embebido en el HTML que solo este servidor sirve) no puede
    disparar acciones."""
    servidor = ServidorMenu()
    try:
        try:
            _post(servidor.url + "accion", {"tipo": "local"})
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("esperaba un 403 sin token")
        assert servidor.esperar_accion(timeout=0.2) is None
    finally:
        servidor.cerrar()


def test_post_accion_con_token_incorrecto_da_403():
    servidor = ServidorMenu()
    try:
        try:
            _post(servidor.url + "accion", {"tipo": "local"}, token="token-adivinado")
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("esperaba un 403 con token incorrecto")
    finally:
        servidor.cerrar()


def test_pagina_principal_incluye_el_token_real():
    """El HTML servido tiene el token embebido (no el placeholder sin
    reemplazar), que es justo lo que lo hace ilegible para un origen ajeno."""
    servidor = ServidorMenu()
    try:
        _, cuerpo = _get(servidor.url)
        assert servidor.token.encode() in cuerpo
        assert b"__JARVIS_TOKEN__" not in cuerpo
    finally:
        servidor.cerrar()


def test_esperar_accion_sin_nada_agota_el_timeout():
    servidor = ServidorMenu()
    try:
        assert servidor.esperar_accion(timeout=0.2) is None
    finally:
        servidor.cerrar()


def test_ruta_desconocida_da_404():
    servidor = ServidorMenu()
    try:
        try:
            _get(servidor.url + "no-existe")
        except urllib.error.HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("esperaba un 404")
    finally:
        servidor.cerrar()
