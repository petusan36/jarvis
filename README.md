# J.A.R.V.I.S.

Asistente personal por voz inspirado en el Jarvis de Iron Man. Te escucha con
**Whisper**, piensa con **Claude** (que puede usar herramientas) y te responde
**hablando**. También tiene un **modo texto** para probarlo sin micrófono.

```
micrófono ──► Whisper (oido.py) ──► Claude + herramientas (cerebro.py) ──► voz (habla.py)
                                      │
                                      └── fecha y hora, calculadora, notas, carpetas, apps…
```

## Requisitos

> ⚠️ **Tiene que ser Python 3.10, 3.11 o 3.12 — ni uno más nuevo.** Kokoro (uno
> de los motores de voz) todavía no soporta 3.13 ni 3.14. Si creas el `.venv`
> con una versión más nueva, `pip install` falla al buscar `kokoro` y no avisa
> por qué. Comprueba tu versión por defecto antes de seguir:
>
> ```bash
> python3 --version
> ```
>
> Si te da 3.13 o más, instala 3.12 aparte (no reemplaza tu Python del
> sistema) y úsalo solo para crear el `.venv` de este proyecto:
>
> | Sistema | Comando |
> |---|---|
> | macOS | `brew install python@3.12` |
> | Ubuntu / Debian | `sudo apt install python3.12 python3.12-venv` |
> | Windows | instala 3.12 desde <https://python.org/downloads> (marca "Add to PATH") |

- Una de estas dos formas de conectar con Claude:
  - **Clave de API** (pago por uso): créala en <https://console.anthropic.com>
  - **Tu suscripción Pro o Max**, a través de Claude Code (ver más abajo)
- **espeak-ng**, para que Kokoro pueda hablar español (ver tabla más abajo)

## Instalación

Un único comando sin extras: `pip install -e .` ya trae todo (texto, voz con
los cuatro motores locales, y el soporte para usar tu suscripción Pro/Max).
Todo lo demás — qué modo usar, y cómo conectar con Claude — se decide después,
desde la propia aplicación (ver más abajo). Las dependencias de desarrollo
(`pytest`) son aparte, ver [Pruebas](#pruebas).

| Sistema | Dependencias | Comando |
|---|---|---|
| Ubuntu / Debian | `sudo apt install libportaudio2 espeak-ng` | |
| macOS | `brew install portaudio espeak-ng` | |
| Windows | `choco install espeak-ng` (o instala el `.msi` de [espeak-ng releases](https://github.com/espeak-ng/espeak-ng/releases)) | |

```bash
git clone git@github.com:petusan36/jarvis.git jarvis
cd jarvis
python3.12 -m venv .venv          # usa EXACTO 3.12 (ver Requisitos arriba)
source .venv/bin/activate        # En Windows: .venv\Scripts\activate
pip install -e .
```

Si al instalar ves `ERROR: Could not find a version that satisfies the
requirement kokoro`, tu `.venv` quedó creado con una versión de Python
equivocada: borralo (`rm -rf .venv`) y repetí desde `python3.12 -m venv .venv`.

## Conectar con Claude: clave de API o suscripción

```bash
python -m jarvis
```

Al primer arranque, Jarvis valida solo cómo conectar con Claude:

- Si encuentra `ANTHROPIC_API_KEY` en tu entorno o `.env`, usa la API.
- Si detecta que ya iniciaste sesión en Claude Code (`claude` → `/login`), usa
  tu suscripción Pro/Max.
- Si no encuentra ninguna de las dos, te pregunta ahí mismo:
  1. **Clave de API**: la pegas y Jarvis la guarda en `.env` por vos.
  2. **Suscripción Pro/Max**: el soporte ya está instalado (no es un extra
     aparte); solo falta que inicies sesión, algo que pip no puede hacer por
     vos:
     ```bash
     npm install -g @anthropic-ai/claude-code   # o el instalador de https://claude.com/claude-code
     claude                                      # dentro, escribe /login e inicia sesión con tu cuenta
     ```
     Hazlo y vuelve a ejecutar `python -m jarvis`.

Una vez configurado cualquiera de los dos, Jarvis lo detecta solo en cada
arranque (o fuérzalo con `JARVIS_MOTOR=api` / `JARVIS_MOTOR=suscripcion`).

Ten en cuenta:

- **Es solo para uso personal en tu equipo.** Las condiciones de Anthropic
  permiten usar tu suscripción con Claude Code y el Agent SDK para uso
  individual, pero no ofrecer tu inicio de sesión a otras personas ni copiar
  tus credenciales a otra aplicación. Si algún día quieres compartir Jarvis,
  cada persona debe usar su propia cuenta o una clave de API.
- **Comparte el límite de uso** con tu Claude Code y claude.ai.
- **Responde algo más lento** que con la API, porque arranca Claude Code por debajo.
- Jarvis desactiva las herramientas propias de Claude Code (terminal, editar
  archivos): solo puede usar las suyas.

## Modo completo (por defecto): voz + HUD

```bash
python -m jarvis
```

Sin ningún flag arranca todo junto: te escucha, te responde hablando y abre en
el navegador la animación estilo Jarvis ([ver más abajo](#animación-hud)).

Jarvis te escucha siempre: habla cuando quieras y, en cuanto hagas una pausa de
menos de un segundo, entiende que has terminado y responde. Mientras él habla
el micrófono se apaga, así que no se escucha a sí mismo. Di **salir** o pulsa
**Ctrl+C** para terminar. La primera vez se descarga el modelo de Whisper
(`small`, unos 500 MB).

- **Sin la animación**: `python -m jarvis --sin-hud` — sigue escuchando y
  hablando, solo que no abre el navegador.
- **Sin voz, solo hablando por texto**: `python -m jarvis --silencio` — te
  sigue escuchando por el micrófono, pero responde solo por texto.
- **Solo cuando le llames**: con `JARVIS_PALABRA_ACTIVACION=jarvis` ignora lo
  que no empiece o contenga «Jarvis» (útil si hay más gente o la tele puesta).
  Admite variantes separadas por comas, p. ej. `jarvis,yarvis`.
- **Si no te detecta o salta con ruido**: ajusta `JARVIS_SENSIBILIDAD_VOZ`
  (por defecto `3`; más bajo detecta voz más baja, más alto ignora más ruido).
- **Modo antiguo**: `python -m jarvis --pulsar` vuelve a pulsar Enter para
  empezar y terminar, en lugar de escuchar siempre.

Con altavoces a mucho volumen y el micrófono del portátil, puede oír el final
de su propia respuesta; si pasa, baja un poco el volumen o usa auriculares.

## Modo texto (sin micrófono ni HUD)

```bash
python -m jarvis --texto
```

```
JARVIS: A su servicio, señor. Escriba 'salir' para terminar.
Tú: ¿qué hora es?
JARVIS: Son las 18:42 del miércoles, señor.
Tú: apunta que mañana tengo que llamar al dentista
JARVIS: Anotado. Ya tiene una nota guardada.
Tú: salir
```

Escribe `/olvidar` para empezar una conversación nueva y `salir` para terminar.
Si además quieres ver la animación mientras escribes: `python -m jarvis --texto --hud`.

## Voz más natural

Jarvis elige solo el mejor motor de voz que tengas disponible, en este orden
(todos ya quedaron instalados con el comando único de arriba, salvo ElevenLabs
que es de pago):

| Motor | Coste | Cómo activarlo |
|---|---|---|
| **ElevenLabs** (voz en la nube, la más natural) | de pago | pon `ELEVENLABS_API_KEY` en el `.env` |
| **Kokoro** (neuronal, en tu equipo) | gratis | nada, ya instalado (necesita `espeak-ng`) |
| **Piper** (neuronal, en tu equipo) | gratis | nada, ya instalado |
| **macOS** (`say`, voces del sistema) | gratis | nada, viene con el Mac |
| pyttsx3 (voces básicas) | gratis | Linux y Windows |

Si un motor falla a mitad de la conversación, Jarvis sigue con el siguiente en
lugar de quedarse mudo. Fuerza uno con `JARVIS_VOZ_MOTOR` y ajusta el ritmo con
`JARVIS_VOZ_VELOCIDAD` (palabras por minuto, por defecto `165`, algo pausado).

**En el Mac, sin instalar nada**: descarga una voz mejorada en *Ajustes del
Sistema → Accesibilidad → Contenido leído → Voz del sistema → Gestionar voces →
Español (España)* y marca **Jorge (Premium)** o **Jorge (mejorada)**. Jarvis la
usa automáticamente; compruébalo con `say -v '?' | grep es_`. Para otra voz:
`JARVIS_VOZ="Jorge (Premium)"`.

**Kokoro** usa por defecto la voz «Alex» (masculina, española, modelo abierto
Apache-2.0; no imita a ningún actor). Descarga el modelo la primera vez desde
Hugging Face. Alternativa: `JARVIS_VOZ=em_santa`.

**Piper** descarga la primera vez la voz `es_ES-davefx-medium` (hombre,
español de España, unos 60 MB) en `~/.jarvis/voces`. Otras voces en
<https://rhasspy.github.io/piper-samples/>; elígela con `JARVIS_VOZ=es_ES-...`.

**ElevenLabs** usa por defecto la voz «George» de su biblioteca: masculina,
británica, cálida y serena, al estilo del mayordomo de la película (no es la
voz del actor ni la imita). Habla en español con el modelo multilingüe.
Puedes elegir otra en <https://elevenlabs.io/app/voice-library> y poner su id
en `JARVIS_ELEVENLABS_VOZ`.

## Animación (HUD)

En el modo completo (por defecto) ya se abre sola: un arco reactor en el
navegador con anillos que reaccionan a lo que hace Jarvis. Para apagarla usa
`--sin-hud`, o enciéndela en modo texto con `--texto --hud`:

```bash
python -m jarvis                  # modo completo: voz + HUD, sin flags
python -m jarvis --texto --hud    # modo texto, con HUD
```

| Estado | Animación |
|---|---|
| En espera | anillos azules girando despacio, el núcleo respira |
| Escuchando | barras alrededor del anillo que vibran con el volumen del micrófono |
| Procesando | los anillos aceleran, se vuelven dorados y aparecen órbitas de escaneo |
| Respondiendo | el núcleo late como si hablara y se muestra la respuesta |

No necesita instalar nada: Jarvis sirve la página en `http://127.0.0.1:8765`
(cámbialo con `JARVIS_PUERTO_HUD`). Pulsa F11 en el navegador para verla a
pantalla completa.

## Carpetas y aplicaciones (macOS)

Jarvis puede manejar tu Mac por voz o texto:

- **Carpetas y archivos**: "¿qué hay en Descargas?", "busca la factura de enero",
  "abre la carpeta Documentos" o "abre el informe.pdf".
- **Aplicaciones**: "abre Spotify", "¿qué programas tengo abiertos?", "cierra Safari".

Por seguridad:

- Solo ve lo que hay dentro de tu carpeta personal (`~`), no el resto del disco.
- No puede borrar ni mover archivos, ni abrir scripts ejecutables.
- Antes de cerrar una aplicación te pregunta y espera a que digas que sí en tu
  siguiente mensaje (podrías tener algo sin guardar).

La primera vez que liste o cierre aplicaciones, macOS te pedirá permiso para
que la Terminal controle "System Events" o esa aplicación: acéptalo (se puede
cambiar en Ajustes del Sistema → Privacidad y seguridad → Automatización).

## Configuración

Todo se ajusta en el archivo `.env` (mira `.env.example`):

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Tu clave de Claude (no hace falta con la suscripción) |
| `JARVIS_MOTOR` | `auto` | `api`, `suscripcion` o `auto` (API si hay clave, si no la suscripción) |
| `JARVIS_NOMBRE_USUARIO` | `señor` | Cómo te llama Jarvis |
| `JARVIS_MODELO` | `claude-opus-5-5` | Modelo de Claude |
| `JARVIS_ESFUERZO` | `low` | `low` responde más rápido; `medium`/`high` piensa más |
| `JARVIS_MODELO_WHISPER` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3` |
| `JARVIS_IDIOMA` | `es` | Idioma de escucha y de voz |
| `JARVIS_CARPETA_DATOS` | `~/.jarvis` | Dónde se guardan las notas |
| `JARVIS_PUERTO_HUD` | `8765` | Puerto local de la animación (`--hud`) |
| `JARVIS_PALABRA_ACTIVACION` | (vacío) | Si se define (p. ej. `jarvis`), solo responde cuando le llamas |
| `JARVIS_SENSIBILIDAD_VOZ` | `3` | Cuánto más alto que el ruido de fondo debe sonar la voz |
| `JARVIS_VOZ_MOTOR` | `auto` | `elevenlabs`, `kokoro`, `piper`, `macos`, `pyttsx3` o `auto` (el mejor disponible) |
| `JARVIS_VOZ` | (vacío) | Nombre de la voz, según el motor (ver "Voz más natural") |
| `JARVIS_VOZ_VELOCIDAD` | `165` | Palabras por minuto |
| `ELEVENLABS_API_KEY` | — | Activa el motor ElevenLabs (de pago) |
| `JARVIS_ELEVENLABS_VOZ` | `JBFqnCBsd6RMkjVDRZzb` (George) | Id de voz de <https://elevenlabs.io/app/voice-library> |
| `JARVIS_ELEVENLABS_MODELO` | `eleven_multilingual_v2` | Modelo de ElevenLabs |

## Estructura

```
jarvis/
├── __main__.py      bucle principal (modo texto y modo voz)
├── cerebro.py       conversación con Claude (API) y ejecución de herramientas
├── cerebro_suscripcion.py  lo mismo usando tu suscripción (Claude Agent SDK)
├── herramientas.py  herramientas que Claude puede usar
├── sistema.py       herramientas de carpetas y aplicaciones (macOS)
├── config.py        configuración desde .env
├── hud/             animación estilo Jarvis (servidor local + hud.html)
└── voz/
    ├── oido.py      micrófono + Whisper (faster-whisper)
    └── habla.py     síntesis de voz (elevenlabs, kokoro, piper, macos, pyttsx3)
tests/               pruebas sin red (cliente de Claude simulado)
```

## Añadir una herramienta

En `jarvis/herramientas.py`, dentro de `_registrar_basicas`:

```python
@self.registrar(
    "clima",
    "Devuelve el tiempo actual en una ciudad.",
    {"ciudad": {"type": "string", "description": "Nombre de la ciudad."}},
)
def clima(ciudad: str) -> str:
    return f"Soleado y 24 °C en {ciudad}"  # aquí llamarías a una API real
```

Claude decide solo cuándo usarla.

## Pruebas

```bash
pip install -e '.[dev]'
pytest
```

Las pruebas no llaman a la API: sustituyen a Claude por un cliente simulado.

## Ideas para seguir

- Interrumpir a Jarvis mientras habla (necesita cancelar el eco de los altavoces)
- Más herramientas: tiempo, calendario, abrir programas, domótica, búsqueda web

## Licencia

MIT
