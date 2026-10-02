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

- Python 3.10, 3.11 o 3.12 (Kokoro, uno de los motores de voz, todavía no
  soporta 3.13 ni 3.14; si ya tienes una versión más nueva, instala 3.12 aparte
  solo para este proyecto)
- Una de estas dos formas de conectar con Claude:
  - **Clave de API** (pago por uso): créala en <https://console.anthropic.com>
  - **Tu suscripción Pro o Max**, a través de Claude Code (ver más abajo)
- **espeak-ng**, para que Kokoro pueda hablar español (ver tabla más abajo)

## Instalación

Un único comando instala todo lo necesario para usar Jarvis: texto y voz (los
cuatro motores locales). Luego, al arrancar, eliges si quieres texto o voz con
un flag — no hace falta reinstalar nada para cambiar de modo. Las dependencias
de desarrollo (`pytest`) son aparte, ver [Pruebas](#pruebas).

| Sistema | Dependencias | Comando |
|---|---|---|
| Ubuntu / Debian | `sudo apt install libportaudio2 espeak-ng` | |
| macOS | `brew install portaudio espeak-ng` | |
| Windows | `choco install espeak-ng` (o instala el `.msi` de [espeak-ng releases](https://github.com/espeak-ng/espeak-ng/releases)) | |

```bash
git clone git@github.com:petusan36/jarvis.git jarvis
cd jarvis
python -m venv .venv
source .venv/bin/activate        # En Windows: .venv\Scripts\activate
pip install -e '.[voz,voz-natural,voz-kokoro]'

cp .env.example .env             # y pon tu clave en ANTHROPIC_API_KEY
```

## Usar tu suscripción de Claude (sin clave de API)

Si tienes Claude Pro o Max, Jarvis puede usar tu suscripción a través de
Claude Code, que se ejecuta en tu equipo con tu propia sesión:

```bash
pip install -e '.[suscripcion]'
npm install -g @anthropic-ai/claude-code   # o el instalador de https://claude.com/claude-code
claude                                      # dentro, escribe /login e inicia sesión con tu cuenta
```

Después, sin `ANTHROPIC_API_KEY` en el `.env`, `python -m jarvis` usa tu
suscripción automáticamente (o fuérzalo con `JARVIS_MOTOR=suscripcion`).

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

## Modo texto (sin micrófono)

```bash
python -m jarvis
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

## Modo voz

Ya quedó instalado con el comando único de arriba. Arranca así:

```bash
python -m jarvis --voz            # te escucha y te responde hablando
python -m jarvis --voz --silencio # te escucha pero responde solo por texto
```

Jarvis te escucha siempre: habla cuando quieras y, en cuanto hagas una pausa de
menos de un segundo, entiende que has terminado y responde. Mientras él habla
el micrófono se apaga, así que no se escucha a sí mismo. Di **salir** o pulsa
**Ctrl+C** para terminar. La primera vez se descarga el modelo de Whisper
(`small`, unos 500 MB).

- **Solo cuando le llames**: con `JARVIS_PALABRA_ACTIVACION=jarvis` ignora lo
  que no empiece o contenga «Jarvis» (útil si hay más gente o la tele puesta).
  Admite variantes separadas por comas, p. ej. `jarvis,yarvis`.
- **Si no te detecta o salta con ruido**: ajusta `JARVIS_SENSIBILIDAD_VOZ`
  (por defecto `3`; más bajo detecta voz más baja, más alto ignora más ruido).
- **Modo antiguo**: `python -m jarvis --voz --pulsar` vuelve a pulsar Enter
  para empezar y terminar.

Con altavoces a mucho volumen y el micrófono del portátil, puede oír el final
de su propia respuesta; si pasa, baja un poco el volumen o usa auriculares.

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

Añade `--hud` para abrir en el navegador un arco reactor con anillos que
reaccionan a lo que hace Jarvis:

```bash
python -m jarvis --voz --hud
python -m jarvis --hud            # también funciona en modo texto
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
