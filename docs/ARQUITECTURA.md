# Arquitectura de Jarvis

Diagrama de alto nivel, hexagonal: `Cerebro` (y `CerebroSuscripcion`) son el
dominio — no conocen Anthropic, OpenAI, Ollama ni Graphiti directamente,
solo los puertos (`ProveedorIA`, `PuertoMemoria`). Los adaptadores concretos
son intercambiables sin tocar el dominio.

```mermaid
flowchart TB
    subgraph Entrada["Punto de entrada"]
        CLI["python -m jarvis\n(__main__.py)"]
        Icono["Ícono de escritorio\n(--instalar-app)\ncopia el bundle PyInstaller\nde dist/, no un lanzador fino"]
    end

    subgraph Menu["Menú de conexión con IA (SIEMPRE corre, cada arranque)"]
        direction TB
        MenuConsola["Consola (hay TTY)\ninput()/print()"]
        MenuVentana["Ventana nativa AppKit\n(sin TTY — ej. ícono de escritorio)\nservidor_menu.py + menu.html\ntoken por sesión + check de Host\n(anti-CSRF/DNS-rebinding)"]
        Login["Login programático\nclaude / codex login\n(subproceso, Terminal.app si hace falta)\nespera y verifica sesión activa"]
    end

    subgraph Dominio["Dominio (jarvis.cerebro)"]
        Cerebro["Cerebro\n(puerto ProveedorIA)"]
        CerebroSus["CerebroSuscripcion\n(Claude Agent SDK + MCP embebido)"]
        Instrucciones["INSTRUCCIONES\n(system prompt, personalidad JARVIS)"]
    end

    subgraph ProveedorIAPuerto["Puerto ProveedorIA"]
        PuertoIA[["ProveedorIA (ABC)"]]
    end

    subgraph Adaptadores["Adaptadores de IA (intercambiables)"]
        AdAnthropic["AdaptadorAnthropic\n(ANTHROPIC_API_KEY en entorno)"]
        AdOllama["AdaptadorOllama\n(local, Qwen3:8b, sin clave)"]
        AdCodex["AdaptadorCodexResponses\n(sesión de codex login,\nendpoint interno chatgpt.com, sin clave)"]
    end

    subgraph Herramientas["Herramientas (tool-calling)"]
        HReg["Herramientas\n(registro + ejecución)"]
        HBuiltin["hora, calcular, notas\n(herramientas.py)"]
        HSistema["sistema.py\ncarpetas, apps, PDFs,\ncerrar app (gate confirmado=true\nen turno posterior)"]
        HMusica["musica.py\nYouTube (autoplay si hay YOUTUBE_API_KEY)"]
        HWeb["web.py\nabrir páginas"]
        HRecordar["recordar\ngate: pedido+confirmación atados,\nturno INMEDIATO siguiente,\nmensaje realmente afirmativo"]
    end

    subgraph Memoria["Memoria permanente (jarvis.memoria)"]
        direction TB
        PuertoMem[["PuertoMemoria (ABC)"]]
        Graphiti["AdaptadorMemoriaGraphiti\nGraphiti: grafo temporal\n(valid_from/valid_to/invalid_at)"]
        Ladybug["LadybugDB\n(grafo+vectores embebido, sin servidor,\nex-Kuzu)"]
        EmbedOllama["Ollama: nomic-embed-text\n(embeddings locales, sin clave)"]
        Archivo["archivo.py: archivado por tamaño fijo\n+ manifiesto + índice invertido tema→chunk\nbúsqueda en frío de 2 pasos\n(~/.jarvis/memoria/)"]
    end

    subgraph Salida["Salida: voz + HUD"]
        Oido["voz/oido.py\nWhisper (entrada)"]
        Habla["voz/habla.py\nKokoro / ElevenLabs / Piper / macOS"]
        Hud["hud/ (HUD + ventana_macos.py)\nanimación nativa o navegador"]
    end

    Config["config.py\nConfig.desde_entorno()\n~/.jarvis/.env"]

    CLI --> Menu
    Icono --> Menu
    MenuConsola --> Config
    MenuVentana --> Config
    Menu -.-> Login
    Login --> Config

    Config --> Cerebro
    Config --> CerebroSus

    Cerebro --> PuertoIA
    PuertoIA --- AdAnthropic
    PuertoIA --- AdOllama
    PuertoIA --- AdCodex

    Cerebro --> Instrucciones
    Cerebro --> HReg
    HReg --- HBuiltin
    HReg --- HSistema
    HReg --- HMusica
    HReg --- HWeb
    HReg --- HRecordar
    HRecordar --> PuertoMem
    PuertoMem --> Graphiti
    Graphiti --> Ladybug
    Graphiti --> EmbedOllama
    Graphiti --> Archivo
    Memoria -. "contexto_relevante()\n(marcado como DATO,\nnunca instrucción —\nanti prompt-injection)" .-> Cerebro

    Cerebro --> Oido
    Cerebro --> Habla
    Cerebro --> Hud
    CerebroSus --> Oido
    CerebroSus --> Habla
    CerebroSus --> Hud
```

## Notas de lectura

- **`Cerebro` vs `CerebroSuscripcion`**: dos implementaciones del mismo rol
  (conversar + ejecutar herramientas), elegidas en `__main__._crear_cerebro`
  según lo que se eligió en el menú. `CerebroSuscripcion` no pasa por el
  puerto `ProveedorIA` — usa el Claude Agent SDK directo, con las
  herramientas de Jarvis expuestas como servidor MCP embebido (mecanismo
  distinto, no un cliente HTTP intercambiable).
- **El menú SIEMPRE corre**, en cada arranque normal — no hay modo "auto"
  que lo saltee por haber algo guardado en `.env`. Si no hay sesión de
  Claude/Codex, el propio menú dispara el login (subproceso, con
  `Terminal.app` visible si no hay tty propia) y espera a que termine antes
  de seguir.
- **Nada de API keys manejadas por Jarvis** en ningún camino, salvo
  `ANTHROPIC_API_KEY` si el usuario la puso directo en el entorno
  (comportamiento preexistente, sin menú). Claude (suscripción) y Codex
  usan sesión ya logueada en su CLI; Ollama no necesita clave.
- **Gates de autorización reales, a nivel de código** (no solo una
  instrucción de prompt que el modelo podría ignorar): `cerrar_aplicacion`
  y `recordar` exigen `confirmado=true` en el turno INMEDIATO siguiente al
  pedido, con el texto real del último mensaje del usuario verificado como
  afirmativo (no solo que el modelo lo diga). Sigue sin existir un
  mecanismo *general* de autorización para cualquier herramienta nueva —
  es ad hoc, herramienta por herramienta, hasta ahora.
- **Memoria se trata como dato, nunca como instrucción**: lo que
  `contexto_relevante()` inyecta en el prompt de `Cerebro` se marca
  explícitamente como información pasada, no como una orden a seguir —
  evita que un hecho guardado se interprete como una instrucción nueva en
  cada conversación futura (inyección de prompt persistente).
- **App de escritorio**: `--instalar-app` construye (o copia, si ya está
  construido) un bundle PyInstaller `--onedir` independiente del repo y del
  `.venv` de desarrollo — verificado corriendo con el repo renombrado. Los
  modelos de voz (Whisper, Kokoro) NO van embebidos: se descargan a la
  caché estándar de cada librería en el primer uso real, igual que
  corriendo desde el repo. Windows/Linux tienen el mismo mecanismo (spec
  cross-platform + CI con matriz de 3 runners), pero solo macOS está
  verificado de punta a punta en esta máquina.
- **Punto de extensión futuro** (decidido, no construido todavía): nuevas
  capacidades no deberían agregar un `.py` por feature — el plan es
  herramientas vía MCP externo + 1-2 herramientas genéricas (código/web),
  con el modelo eligiendo cuál usar según la tarea.
