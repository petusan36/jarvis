"""Herramientas que Claude puede usar.

Para añadir una herramienta nueva: escribe una función que devuelva un str y
regístrala con el decorador ``@herramienta`` indicando su esquema JSON.
"""

from __future__ import annotations

import ast
import json
import math
import operator
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .autorizacion import Autorizacion

if TYPE_CHECKING:
    from .config import Config
    from .memoria.puerto import PuertoMemoria


# Letras, dígitos, espacios y la puntuación habitual en nombres/apodos. Ver
# guardar_nombre: nada de saltos de línea, comillas ni signos que puedan
# escapar el formato CLAVE=valor de .env o leerse como una instrucción.
_NOMBRE_VALIDO = re.compile(r"[\w .'-]+")


@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    parametros: dict[str, Any]
    funcion: Callable[..., str]
    # True para herramientas que ejecutan una acción real (abrir algo, cerrar
    # algo, escribir algo), no solo informar. Ver reconocimiento de voz del
    # usuario (jarvis.voz.hablante) y Herramientas.ejecutar: si la voz de
    # quien habla no es la del dueño de Jarvis, estas herramientas se niegan
    # a ejecutarse en lugar de hacerlo para cualquiera que hable cerca del
    # micrófono.
    requiere_dueño: bool = False

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
        web: bool = True,
        youtube_api_key: str = "",
        memoria: "PuertoMemoria | None" = None,
        config: "Config | None" = None,
    ):
        self.carpeta_datos = carpeta_datos
        self._registro: dict[str, Herramienta] = {}
        # Cuenta los mensajes del usuario; sirve para exigir confirmaciones en un mensaje aparte.
        self.turno = 0
        # Último mensaje tal cual lo escribió/dijo el usuario, para que una
        # confirmación (ver "recordar") pueda verificar que de verdad dijo
        # algo afirmativo, no solo que pasó un turno — sin esto, un mensaje
        # inyectado (ej. desde una página web que Jarvis lea) podía hacer
        # que el modelo llamara confirmado=true sin que el usuario dijera
        # nada parecido a un sí.
        self.ultimo_mensaje_usuario = ""
        # El bucle principal revisa esto después de cada respuesta para saber si debe terminar.
        self.salir_pedido = False
        # Puerto de memoria permanente (ver jarvis.memoria). Si es None, la
        # herramienta "recordar" no se registra y Cerebro no inyecta
        # contexto de memoria en el prompt: Jarvis sigue funcionando igual
        # que antes de esta tarea.
        self.memoria = memoria
        # Compartida por cualquier herramienta que necesite confirmación en dos
        # pasos (ver jarvis.autorizacion): "recordar" acá, "cerrar_aplicacion" en
        # sistema.py, y cualquier herramienta futura que la necesite.
        self.autorizacion = Autorizacion()
        # Si quien habla en este turno es (o se asume que es, cuando no hay
        # reconocimiento de voz activo) el dueño de Jarvis. Lo fija
        # nuevo_turno; ejecutar() lo revisa antes de correr una herramienta
        # marcada con requiere_dueño=True. Por defecto True: sin verificador
        # de hablante configurado (ver jarvis.voz.hablante), Jarvis se
        # comporta como siempre, sin exigir nada.
        self.es_dueño_quien_habla = True
        # El bucle principal revisa esto después de cada respuesta, igual que
        # salir_pedido: si está en True, pone a Oido en modo de escucha
        # pasiva (ver jarvis.voz.oido.Oido.dormir) y lo resetea.
        self.dormir_pedido = False
        self._registrar_basicas()
        if sistema:
            from .sistema import registrar_sistema
            registrar_sistema(self)
        from .musica import registrar_musica
        registrar_musica(self, youtube_api_key)
        if web:
            from .web import registrar_web
            registrar_web(self)
        if memoria is not None:
            self._registrar_memoria(memoria)
        if config is not None:
            self._registrar_identidad(config)
        self._registrar_habilidades()

    def nuevo_turno(self, texto_usuario: str = "", es_dueño: bool = True) -> None:
        """Avisa de que ha llegado un mensaje nuevo del usuario.

        ``es_dueño`` lo decide la capa de voz (ver jarvis.voz.hablante): si
        hay un verificador de hablante configurado y la grabación de este
        turno no coincide con la voz enrolada, llega en False."""
        self.turno += 1
        self.ultimo_mensaje_usuario = texto_usuario
        self.es_dueño_quien_habla = es_dueño

    def registrar(self, nombre: str, descripcion: str, parametros: dict[str, Any],
                  requiere_dueño: bool = False):
        def decorador(funcion: Callable[..., str]) -> Callable[..., str]:
            self._registro[nombre] = Herramienta(nombre, descripcion, parametros, funcion, requiere_dueño)
            return funcion

        return decorador

    def definiciones(self) -> list[dict[str, Any]]:
        return [h.definicion() for h in self._registro.values()]

    def ejecutar(self, nombre: str, argumentos: dict[str, Any]) -> tuple[str, bool]:
        """Ejecuta una herramienta. Devuelve (resultado, es_error)."""
        herramienta = self._registro.get(nombre)
        if herramienta is None:
            return f"Herramienta desconocida: {nombre}", True
        if herramienta.requiere_dueño and not self.es_dueño_quien_habla:
            return (
                f"No puedo ejecutar «{nombre}»: la voz de quien lo pidió no es la de "
                "quien tiene autorizado Jarvis. Decímelo con tu propia voz."
            ), False
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
            requiere_dueño=True,
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
            "Cierra Jarvis. Llamala SIEMPRE que el usuario exprese, de cualquier forma, "
            "que quiere terminar o salir — no solo con la palabra exacta 'salir'. Ejemplos "
            "reales que SÍ cuentan: 'cerrate', 'listo, salí de la app', 'ya terminamos por "
            "hoy', 'gracias Jarvis, por ahora solo salir', 'eso es todo'. Si decís en tu "
            "respuesta que vas a cerrar o despedirte, tenés que haber llamado esta "
            "herramienta en la MISMA respuesta — nunca digas que cerrás sin llamarla, "
            "porque si no la llamás Jarvis sigue abierto esperando otro mensaje. No hace "
            "falta confirmar: a diferencia de cerrar otra aplicación, aquí no hay nada que perder.",
            {},
            requiere_dueño=True,
        )
        def cerrar_jarvis() -> str:
            self.salir_pedido = True
            return "Cerrando Jarvis."

        @self.registrar(
            "dormir_jarvis",
            "Activa el modo de escucha pasiva: Jarvis deja de responder a lo que se "
            "diga hasta que lo vuelvan a nombrar (decir 'Jarvis'). Llamala cuando el "
            "usuario pida explícitamente que se quede callado, que 'duerma' o "
            "'descanse' por ahora — a diferencia de cerrar_jarvis, la app sigue "
            "corriendo y vuelve a escuchar normal en cuanto lo nombren.",
            {},
            requiere_dueño=True,
        )
        def dormir_jarvis() -> str:
            self.dormir_pedido = True
            return "Entrando en modo de escucha pasiva. Decí «Jarvis» cuando quieras que vuelva."

    def _registrar_identidad(self, config: "Config") -> None:
        @self.registrar(
            "guardar_nombre",
            "Guarda cómo quiere que le hables al usuario (su nombre o cómo prefiere "
            "que lo llames) para dirigirte así a él en esta y en futuras conversaciones. "
            "Llamala en cuanto te lo diga, sin pedir confirmación — no es información "
            "sensible, y el usuario puede cambiarlo en cualquier momento volviendo a "
            "decírtelo.",
            {"nombre": {"type": "string", "description": "Cómo dirigirte al usuario, p. ej. 'Pedro' o 'jefe'."}},
            requiere_dueño=True,
        )
        def guardar_nombre(nombre: str) -> str:
            nombre = nombre.strip()
            # Validación estricta, no solo "no vacío": este valor se escribe
            # tal cual en .env (una línea CLAVE=valor) y se repite en el
            # system prompt de TODAS las conversaciones futuras (ver
            # cerebro.INSTRUCCIONES). Sin esto, un salto de línea en nombre
            # inyectaría líneas nuevas en .env (podría pisar cualquier otra
            # variable, incluida ANTHROPIC_API_KEY), y un texto largo tipo
            # instrucción quedaría persistido como inyección de prompt
            # permanente — el usuario nunca escribe esto directo, lo manda
            # el modelo, que podría haber leído algo malicioso (p. ej. una
            # página web) que le diga que llame a esta herramienta.
            if not 1 <= len(nombre) <= 40 or not _NOMBRE_VALIDO.fullmatch(nombre):
                raise ValueError(
                    "ese nombre no es válido: máximo 40 caracteres, sin saltos de línea "
                    "ni símbolos raros — solo letras, espacios y guiones."
                )
            from .config import guardar_en_env

            guardar_en_env("JARVIS_NOMBRE_USUARIO", nombre)
            os.environ["JARVIS_NOMBRE_USUARIO"] = nombre
            config.nombre_usuario = nombre
            return f"Listo, te voy a llamar {nombre} de ahora en más."

    def _registrar_memoria(self, memoria: "PuertoMemoria") -> None:
        @self.registrar(
            "recordar",
            "Guarda en la memoria permanente de Jarvis un hecho sobre el usuario "
            "(preferencias, datos personales, rutinas...) para recordarlo en futuras "
            "conversaciones, incluso después de cerrar Jarvis. Si el hecho actualiza uno "
            "anterior (por ejemplo, un cambio de preferencia), el anterior queda "
            "reemplazado automáticamente, sin quedar contradictorio. Úsala solo cuando el "
            "usuario comparta algo que valga la pena recordar a futuro, no para cada dato "
            "suelto de la conversación. Llámala primero con confirmado=false: eso deja el "
            "guardado pendiente. Dile al usuario qué vas a recordar y espera su respuesta. "
            "Solo si en su siguiente mensaje confirma, vuelve a llamarla con confirmado=true.",
            {
                "hecho": {
                    "type": "string",
                    "description": "Qué tipo de hecho es, en pocas palabras, p. ej. 'género de música preferido'.",
                },
                "valor": {
                    "type": "string",
                    "description": "El valor del hecho, p. ej. 'rock'.",
                },
                "confirmado": {
                    "type": "boolean",
                    "description": "true solo si el usuario ya confirmó que quiere que se guarde esto.",
                },
            },
            requiere_dueño=True,
        )
        def recordar(hecho: str, valor: str, confirmado: bool) -> str:
            clave = ("recordar", hecho.strip().lower(), valor.strip().lower())
            if not self.autorizacion.pedir(clave, self.turno, confirmado, self.ultimo_mensaje_usuario):
                return (f"Guardar «{hecho}: {valor}» en memoria, pendiente de confirmar. "
                        "Pregúntale al usuario si quiere que lo recuerdes y esperá su "
                        "respuesta antes de llamar de nuevo con confirmado=true.")
            return memoria.recordar(hecho, valor)

    def _registrar_habilidades(self) -> None:
        from .habilidades import guardar_habilidad, leer_habilidad, listar_habilidades

        carpeta = self.carpeta_datos / "habilidades"

        @self.registrar(
            "crear_habilidad",
            "Guarda (o mejora, si ya existe una con el mismo nombre) un procedimiento "
            "propio para usarlo en esta y futuras conversaciones — al estilo de un "
            "archivo de skill, NUNCA código que se ejecute. Usala cuando descubras una "
            "forma útil de hacer algo que probablemente se repita, no para algo de una "
            "sola vez. Para mejorar una que ya tenés, llamala de nuevo con el mismo "
            "nombre y el procedimiento actualizado: reemplaza a la anterior entera, no "
            "la combina. Llamala primero con confirmado=false: eso deja el guardado "
            "pendiente. Mostrale al usuario el nombre, la descripción Y el procedimiento "
            "completo antes de guardar nada — nunca en silencio — y esperá su respuesta. "
            "Solo si en su siguiente mensaje confirma, volvé a llamarla con "
            "confirmado=true. El contenido de una habilidad se sigue como instrucción en "
            "el futuro, así que esta confirmación importa más que la de cualquier otra "
            "herramienta.",
            {
                "nombre": {"type": "string", "description": "Nombre corto, p. ej. 'resumen-pdf-largo'."},
                "descripcion": {"type": "string", "description": "Una línea: para qué sirve esta habilidad."},
                "contenido": {"type": "string", "description": "El procedimiento completo, en tus palabras."},
                "confirmado": {
                    "type": "boolean",
                    "description": "true solo si el usuario ya confirmó, viendo el procedimiento completo.",
                },
            },
            requiere_dueño=True,
        )
        def crear_habilidad(nombre: str, descripcion: str, contenido: str, confirmado: bool) -> str:
            clave = ("crear_habilidad", nombre.strip().lower())
            if not self.autorizacion.pedir(clave, self.turno, confirmado, self.ultimo_mensaje_usuario):
                return (
                    f"Guardar la habilidad «{nombre}» pendiente de confirmar. Mostrale al "
                    "usuario el nombre, la descripción y el procedimiento completo, y "
                    "esperá su respuesta antes de llamar de nuevo con confirmado=true."
                )
            ruta = guardar_habilidad(carpeta, nombre, descripcion, contenido)
            return f"Habilidad «{ruta.stem}» guardada: {descripcion}"

        @self.registrar(
            "listar_habilidades",
            "Lista las habilidades propias que ya tenés guardadas (nombre y para qué "
            "sirve cada una), sin el procedimiento completo.",
            {},
        )
        def listar_habilidades_tool() -> str:
            habilidades = listar_habilidades(carpeta)
            if not habilidades:
                return "No tengo ninguna habilidad propia guardada todavía."
            return "\n".join(f"- {nombre}: {descripcion}" for nombre, descripcion in habilidades)

        @self.registrar(
            "leer_habilidad",
            "Lee el procedimiento completo de una habilidad propia guardada, para "
            "seguirlo. Usala cuando listar_habilidades (o el resumen que ya tenés a la "
            "vista) diga que una de tus habilidades aplica a lo que te están pidiendo.",
            {"nombre": {"type": "string", "description": "Nombre de la habilidad, como aparece en listar_habilidades."}},
        )
        def leer_habilidad_tool(nombre: str) -> str:
            return leer_habilidad(carpeta, nombre)

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
