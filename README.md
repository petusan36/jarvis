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

## Conectar con un modelo de IA: el menú de cada arranque

```bash
python -m jarvis
```

En **todo** arranque normal (sin `--instalar-app`) Jarvis te pregunta, con un
menú de dos niveles, cómo conectar con un modelo de IA — no solo la primera
vez: así podés cambiar de proveedor sin pasar ningún flag.

1. **Nivel 1**: ¿modelo local o proveedor en la nube?
2. **Nivel 2** (solo si elegís proveedor): ¿OpenAI (Codex) o Anthropic (Claude)?

- **Local (Ollama)**: lista los modelos que ya tengas instalados y elegís uno.
- **OpenAI / Codex**: usa la sesión de Codex CLI. Si todavía no iniciaste
  sesión, Jarvis mismo ejecuta `codex login` (hereda la terminal para que
  completes el inicio de sesión en el navegador), espera a que termine y
  recién ahí arranca.
- **Anthropic / Claude**: usa tu suscripción Pro/Max a través de Claude Code.
  Si no hay sesión, Jarvis abre `claude` (la propia CLI interactiva — Claude
  Code no tiene, al momento de escribir esto, un subcomando de login no
  interactivo): dentro, escribe `/login`, completa el inicio de sesión y
  salí con `/exit` o Ctrl+D para volver. Jarvis espera a que ese proceso
  termine y verifica que la sesión quedó activa antes de arrancar.

Ninguna opción pide ni guarda una clave de API: solo se persiste en `.env` la
elección en sí (qué motor usar, qué modelo local), nunca un secreto. La
clave directa de Anthropic (`ANTHROPIC_API_KEY`) sigue funcionando si la
ponés vos mismo en `.env` y elegís Anthropic en el menú (o la sesión de
Claude Code), pero el menú ya no la pide ni la pega por vos.

El menú se muestra por terminal (`input()`/`print()`) si hay una terminal
interactiva de verdad. Si no (ej. doble clic en el ícono de escritorio, sin
terminal) pero hay entorno gráfico disponible (hoy: macOS con PyObjC), se
muestra en cambio una ventana nativa con el mismo menú de 2 niveles: elegir
modelo local o proveedor, y si hace falta loguearse, se abre una Terminal.app
visible con `claude`/`codex login` mientras la ventana espera y pollea hasta
detectar la sesión activa. Sin terminal ni entorno gráfico, no hay forma de
mostrar el menú y Jarvis falla con un mensaje claro.

`--reconfigurar-ia` ya no tiene efecto propio (el menú corre siempre); se
conserva solo por compatibilidad con scripts o accesos existentes.

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
menos de un segundo, entiende que has terminado y responde. Di **salir** o
pulsa **Ctrl+C** para terminar. La primera vez se descarga el modelo de
Whisper (`small`, unos 500 MB).

- **Interrumpirlo mientras habla**: decí **"Jarvis"** y corta la respuesta al
  instante (solo con los motores Kokoro, Piper o ElevenLabs — `say` de macOS
  y pyttsx3 no se pueden cortar a mitad de frase). Sin cancelación de eco: con
  parlantes el micrófono capta su propia voz mientras habla, así que en
  teoría podría confundirse con algo que él mismo dijo, aunque es poco común
  porque sus respuestas casi nunca se nombran a sí mismas. Con auriculares no
  pasa.
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
| Respondiendo | el núcleo late como si hablara |

No necesita instalar nada extra: Jarvis sirve la página en
`http://127.0.0.1:8765` (cámbialo con `JARVIS_PUERTO_HUD`).

**En macOS**, se abre sola como una ventana flotante nativa: sin marco, sin
botones, fondo transparente (se ve el escritorio detrás) y sin texto —
solo los anillos, como un widget que flota sobre todo lo demás. Chica,
proporcional al tamaño de tu pantalla, y siempre arriba a la izquierda. Se
puede arrastrar agarrando cualquier parte (no tiene barra de título). No
aparece en el Dock ni en el selector de apps — para cerrarla, cerrá Jarvis
(decile "cerrate").

En Windows y Linux, por ahora sigue abriéndose como ventana de Chrome en modo
app (sin pestañas ni barra de direcciones, pero con el marco normal) o, sin
Chrome instalado, como pestaña del navegador.

## App de escritorio

El ícono de escritorio es una copia **standalone** de Jarvis, construida con
[PyInstaller](https://pyinstaller.org/): no depende de este repo, de este
venv ni de ningún Python instalado en el sistema para arrancar. Si movés o
borrás el repo clonado, el ícono sigue funcionando — la copia instalada ya
tiene adentro todo lo que necesita (intérprete, torch, el motor de voz, etc).

### 1. Construir el bundle (una vez por sistema)

```bash
pip install -e ".[build]"   # instala PyInstaller (herramienta de build, no de runtime)
scripts/build_app.sh        # tarda varios minutos la primera vez
```

Esto genera:

- macOS: `dist/Jarvis.app`
- Windows/Linux: `dist/jarvis/` (carpeta con `jarvis.exe` o el binario `jarvis` adentro)

PyInstaller **no cruza plataformas**: un build hecho en Mac solo corre en
Mac. Para generar los otros dos, o corré `scripts/build_app.sh` (Linux) /
`pyinstaller --noconfirm --clean jarvis.spec` (Windows, desde PowerShell) en
esa máquina, o descargá el artifact ya construido del workflow de CI
(`.github/workflows/build-app.yml`, corre en una matriz de runners macOS +
Windows + Linux y sube cada bundle como artifact de GitHub Actions).

**Tamaño aproximado:** el bundle pesa alrededor de **1 GB** (torch y
transformers, que usa Kokoro para el TTS, son el grueso). Los modelos de voz
en sí — Whisper ("small", ~500 MB) y las voces de Kokoro/Piper — **no están
embebidos**: se descargan solos la primera vez que se usan, igual que
corriendo desde el repo (ver tabla de abajo).

### 2. Instalar el ícono de escritorio

```bash
python -m jarvis --instalar-app
```

Copia el bundle ya construido (paso 1) al lugar de escritorio de cada
sistema. Si todavía no corriste `scripts/build_app.sh`, este comando falla
con un mensaje claro pidiendo que lo corras primero.

| Sistema | Dónde queda | Qué copia |
|---|---|---|
| macOS | `~/Applications/Jarvis.app` (Finder, Launchpad, Spotlight) | `dist/Jarvis.app` completo |
| Windows | Menú Inicio → Jarvis (lanza `jarvis.exe` directo, sin consola) | `dist/jarvis/` a `%LOCALAPPDATA%\Jarvis\app` |
| Linux | menú de aplicaciones del escritorio (`~/.local/share/applications`) | `dist/jarvis/` a `~/.local/share/jarvis/app` |

Importante:

- **El ícono de escritorio en macOS sí puede elegir o cambiar de proveedor**,
  mostrando el menú en una ventana nativa en vez de una terminal (ver más
  arriba) — requiere PyObjC instalado, igual que la ventana flotante del HUD.
  En Windows y Linux el ícono todavía no tiene ventana propia para esto: ahí
  seguí usando el binario del bundle (o `python -m jarvis`) desde una
  terminal para la primera conexión o para cambiar de proveedor.
- **macOS puede avisar "desarrollador no identificado"** la primera vez que
  abras el ícono (no está firmado ni notarizado): clic derecho → Abrir, o
  `xattr -d com.apple.quarantine ~/Applications/Jarvis.app`.
- No hay ícono con arte personalizado ni desinstalador todavía — borrar la
  carpeta instalada a mano alcanza para quitarlo (`rm -rf
  ~/Applications/Jarvis.app` en macOS; `%LOCALAPPDATA%\Jarvis` + el `.bat`
  del menú Inicio en Windows; `~/.local/share/jarvis` + el `.desktop` en
  Linux).
- Dónde se descargan los modelos en el primer uso real (sin cambios respecto
  a correr desde el repo):

  | Modelo | Carpeta |
  |---|---|
  | Whisper (voz → texto, `faster-whisper`) | caché de huggingface (`~/.cache/huggingface`) |
  | Kokoro (texto → voz) | caché de huggingface (`~/.cache/huggingface`) |
  | Piper (texto → voz, alternativa) | `~/.jarvis/voces` |

- Este paso prepara el terreno para que la animación HUD, más adelante, flote
  directamente en el escritorio en vez de abrirse en una pestaña del navegador.

## Carpetas y aplicaciones (macOS)

Jarvis puede manejar tu Mac por voz o texto:

- **Carpetas y archivos**: "¿qué hay en Descargas?", "busca la factura de enero",
  "abre la carpeta Documentos" o "abre el informe.pdf".
- **Leer PDFs**: "leé el informe.pdf de Documentos y resumímelo" — extrae el
  texto para que Jarvis lo lea, resuma o responda preguntas sobre él (no
  funciona con PDFs escaneados sin OCR, que no tienen texto real adentro).
- **Aplicaciones**: "abre Spotify", "¿qué programas tengo abiertos?", "cierra Safari".

Por seguridad:

- Solo ve lo que hay dentro de tu carpeta personal (`~`), no el resto del disco.
- No puede borrar ni mover archivos, ni abrir scripts ejecutables.
- Antes de cerrar una aplicación te pregunta y espera a que digas que sí en tu
  siguiente mensaje (podrías tener algo sin guardar). Para cerrar Jarvis mismo
  no hace falta esa confirmación: decile "cerrate" o "salí" y termina.

La primera vez que liste o cierre aplicaciones, macOS te pedirá permiso para
que la Terminal controle "System Events" o esa aplicación: acéptalo (se puede
cambiar en Ajustes del Sistema → Privacidad y seguridad → Automatización).

## Música (YouTube)

"Poné Bohemian Rhapsody" o "buscá música de Serrat" abre YouTube con esa
búsqueda. Para que reproduzca directo el primer resultado sin que tengas que
clickear nada, consigue una clave de **YouTube Data API v3** (gratis, con
cuota) en <https://console.cloud.google.com/apis/library/youtube.googleapis.com>
y ponla en `YOUTUBE_API_KEY`. Sin ella, igual funciona: abre los resultados y
elegís vos.

## Navegar por internet

Para lo que no sea específicamente música en YouTube: "abrí Spotify" o
"buscá las noticias de hoy" abren el navegador — una URL directa si la das,
o una búsqueda en Google si no.

## Configuración

Todo se ajusta en el archivo `.env` (mira `.env.example`):

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Tu clave de Claude (no hace falta con la suscripción) |
| `JARVIS_MOTOR` | `auto` | `api`, `suscripcion` o `codex`. El menú de cada arranque lo elige y lo guarda acá; no hace falta tocarlo a mano. |
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
| `YOUTUBE_API_KEY` | — | Reproduce directo el primer resultado al pedir música; sin ella, abre los resultados |

## Estructura

```
jarvis/
├── __main__.py      bucle principal (modo texto y modo voz)
├── cerebro.py       conversación con Claude (API) y ejecución de herramientas
├── cerebro_suscripcion.py  lo mismo usando tu suscripción (Claude Agent SDK)
├── herramientas.py  herramientas que Claude puede usar
├── sistema.py       herramientas de carpetas, aplicaciones y PDFs (macOS)
├── musica.py        buscar y reproducir música en YouTube
├── web.py           abrir páginas web / buscar en Google
├── config.py        configuración desde .env
├── escritorio.py    ícono de escritorio (--instalar-app)
├── hud/             animación estilo Jarvis (servidor local + hud.html)
│   └── ventana_macos.py  ventana flotante nativa sin marco (macOS, PyObjC)
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
