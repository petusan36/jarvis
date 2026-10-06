"""Herramientas que Claude puede usar.

Para añadir una herramienta nueva: escribe una función que devuelva un str y
regístrala con el decorador ``@herramienta`` indicando su esquema JSON.
"""

from __future__ import annotations

import ast
import json
import math
import operator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .memoria.puerto import PuertoMemoria


@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    parametros: dict[str, Any]
    funcion: Callable[..., str]

    def definicion(self) -> dict[str, Any]:
        """Definición en el formato que espera la API de Claude."""
        return {
            "name": self.nombre,
            "description": self.descripcion,
            "input_schema": {
                "type": "object",
                "properties": self.parametros,
                "required": list(self.parametros),
                "additionalProperties": False,
            },
            "strict": True,
        }


class Herramientas:
    """Registro de herramientas disponibles para una sesión."""

    def __init__(
        self,
        carpeta_datos: Path,
        sistema: bool = True,
        youtube_api_key: str = "",
        memoria: "PuertoMemoria | None" = None,
    ):
        self.carpeta_datos = carpeta_datos
        self._registro: dict[str, Herramienta] = {}
        # Cuenta los mensajes del usuario; sirve para exigir confirmaciones en un mensaje aparte.
        self.turno = 0
        # El bucle principal revisa esto después de cada respuesta para saber si debe terminar.
        self.salir_pedido = False
        # Puerto de memoria permanente (ver jarvis.memoria). Si es None, la
        # herramienta "recordar" no se registra y Cerebro no inyecta
        # contexto de memoria en el prompt: Jarvis sigue funcionando igual
        # que antes de esta tarea.
        self.memoria = memoria
        self._registrar_basicas()
        if sistema:
            from .sistema import registrar_sistema
            registrar_sistema(self)
        from .musica import registrar_musica
        registrar_musica(self, youtube_api_key)
        from .web import registrar_web
        registrar_web(self)
        if memoria is not None:
            self._registrar_memoria(memoria)

    def nuevo_turno(self) -> None:
        """Avisa de que ha llegado un mensaje nuevo del usuario."""
        self.turno += 1

    def registrar(self, nombre: str, descripcion: str, parametros: dict[str, Any]):
        def decorador(funcion: Callable[..., str]) -> Callable[..., str]:
            self._registro[nombre] = Herramienta(nombre, descripcion, parametros, funcion)
            return funcion

        return decorador

    def definiciones(self) -> list[dict[str, Any]]:
        return [h.definicion() for h in self._registro.values()]

    def ejecutar(self, nombre: str, argumentos: dict[str, Any]) -> tuple[str, bool]:
        """Ejecuta una herramienta. Devuelve (resultado, es_error)."""
        herramienta = self._registro.get(nombre)
        if herramienta is None:
            return f"Herramienta desconocida: {nombre}", True
        try:
            return herramienta.funcion(**argumentos), False
        except Exception as error:  # el error vuelve a Claude para que lo explique
            return f"Error al ejecutar {nombre}: {error}", True

    # --- herramientas incluidas -------------------------------------------

    def _registrar_basicas(self) -> None:
        @self.registrar(
            "fecha_y_hora",
            "Devuelve la fecha y la hora actuales del equipo del usuario.",
            {},
        )
        def fecha_y_hora() -> str:
            return datetime.now().strftime("%A %d/%m/%Y, %H:%M")

        @self.registrar(
            "calcular",
            "Evalúa una expresión matemática (+ - * / ** %, paréntesis, sqrt, sin, cos, "
            "tan, log, pi, e). Úsala para cualquier cálculo en lugar de calcular de memoria.",
            {"expresion": {"type": "string", "description": "Por ejemplo: (2+3)*sqrt(16)"}},
        )
        def calcular(expresion: str) -> str:
            return str(evaluar_expresion(expresion))

        @self.registrar(
            "guardar_nota",
            "Guarda una nota o recordatorio del usuario para consultarlo más tarde.",
            {"texto": {"type": "string", "description": "Contenido de la nota."}},
        )
        def guardar_nota(texto: str) -> str:
            notas = self._leer_notas()
            notas.append({"fecha": datetime.now().isoformat(timespec="minutes"), "texto": texto})
            self._ruta_notas().parent.mkdir(parents=True, exist_ok=True)
            self._ruta_notas().write_text(json.dumps(notas, ensure_ascii=False, indent=2), "utf-8")
            return f"Nota guardada. Hay {len(notas)} nota(s)."

        @self.registrar(
            "leer_notas",
            "Devuelve todas las notas y recordatorios guardados por el usuario.",
            {},
        )
        def leer_notas() -> str:
            notas = self._leer_notas()
            if not notas:
                return "No hay notas guardadas."
            return "\n".join(f"- [{n['fecha']}] {n['texto']}" for n in notas)

        @self.registrar(
            "cerrar_jarvis",
            "Cierra Jarvis. Úsala cuando el usuario pida salir, cerrar la aplicación, "
            "terminar, o se despida dejando claro que ya terminó (por ejemplo 'cerrate', "
            "'listo, salí de la app', 'ya terminamos por hoy'). No hace falta confirmar: "
            "a diferencia de cerrar otra aplicación, aquí no hay nada que perder.",
            {},
        )
        def cerrar_jarvis() -> str:
            self.salir_pedido = True
            return "Cerrando Jarvis."

    def _registrar_memoria(self, memoria: "PuertoMemoria") -> None:
        @self.registrar(
            "recordar",
            "Guarda en la memoria permanente de Jarvis un hecho sobre el usuario "
            "(preferencias, datos personales, rutinas...) para recordarlo en futuras "
            "conversaciones, incluso después de cerrar Jarvis. Si el hecho actualiza uno "
            "anterior (por ejemplo, un cambio de preferencia), el anterior queda "
            "reemplazado automáticamente, sin quedar contradictorio. Úsala solo cuando el "
            "usuario comparta algo que valga la pena recordar a futuro, no para cada dato "
            "suelto de la conversación.",
            {
                "hecho": {
                    "type": "string",
                    "description": "Qué tipo de hecho es, en pocas palabras, p. ej. 'género de música preferido'.",
                },
                "valor": {
                    "type": "string",
                    "description": "El valor del hecho, p. ej. 'rock'.",
                },
            },
        )
        def recordar(hecho: str, valor: str) -> str:
            return memoria.recordar(hecho, valor)

    def _ruta_notas(self) -> Path:
        return self.carpeta_datos / "notas.json"

    def _leer_notas(self) -> list[dict[str, str]]:
        ruta = self._ruta_notas()
        if not ruta.is_file():
            return []
        return json.loads(ruta.read_text("utf-8"))


_OPERADORES = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_NOMBRES = {"pi": math.pi, "e": math.e}
_FUNCIONES = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
              "log": math.log, "abs": abs, "round": round}


def evaluar_expresion(expresion: str) -> float | int:
    """Evalúa aritmética de forma segura (sin eval)."""

    def visitar(nodo: ast.AST):
        if isinstance(nodo, ast.Expression):
            return visitar(nodo.body)
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)):
            return nodo.value
        if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERADORES:
            return _OPERADORES[type(nodo.op)](visitar(nodo.left), visitar(nodo.right))
        if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _OPERADORES:
            return _OPERADORES[type(nodo.op)](visitar(nodo.operand))
        if isinstance(nodo, ast.Name) and nodo.id in _NOMBRES:
            return _NOMBRES[nodo.id]
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                and nodo.func.id in _FUNCIONES and not nodo.keywords):
            return _FUNCIONES[nodo.func.id](*(visitar(a) for a in nodo.args))
        raise ValueError("expresión no permitida")

    return visitar(ast.parse(expresion.replace("^", "**"), mode="eval"))
