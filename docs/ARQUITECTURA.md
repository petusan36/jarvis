# Arquitectura de Jarvis

Diagrama de alto nivel, hexagonal: `Cerebro` (y `CerebroSuscripcion`) son el
dominio — no conocen Anthropic, OpenAI, Ollama ni Graphiti directamente,
solo los puertos (`ProveedorIA`, `PuertoMemoria`). Los adaptadores concretos
son intercambiables sin tocar el dominio.

```mermaid
flowchart TB
    subgraph Entrada["Punto de entrada"]
        CLI["python -m jarvis\n(__main__.py)"]
        Icono["Ícono de escritorio\n(--instalar-app)"]
    end

    subgraph Menu["Menú de conexión con IA (cada arranque)"]
        direction TB
        MenuConsola["Consola (hay TTY)"]
        MenuVentana["Ventana nativa AppKit\n(sin TTY, servidor_menu.py + menu.html)"]
        Login["Login programático\nclaude / codex login\n(subproceso, Terminal.app si hace falta)"]
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
        HSistema["sistema.py\ncarpetas, apps, PDFs, cerrar Jarvis"]
        HMusica["musica.py\nYouTube (autoplay si hay YOUTUBE_API_KEY)"]
        HWeb["web.py\nabrir páginas"]
        HRecordar["recordar\n(memoria — EN CONSTRUCCIÓN)"]
    end

    subgraph MemoriaWIP["Memoria permanente — EN CONSTRUCCIÓN"]
        direction TB
        PuertoMem[["PuertoMemoria (ABC)"]]
        Graphiti["Graphiti\n(grafo temporal: valid_from/to/invalid_at)"]
        Ladybug["LadybugDB\n(grafo+vectores embebido, sin servidor)"]
        EmbedOllama["Ollama: nomic-embed-text\n(embeddings locales, sin clave)"]
        Archivo["Archivado por tamaño fijo\n+ manifiesto + índice invertido\n(~/.jarvis/memoria/)"]
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
    HReg -.-> HRecordar
    HRecordar -.-> PuertoMem
    PuertoMem -.-> Graphiti
    Graphiti -.-> Ladybug
    Graphiti -.-> EmbedOllama
    Graphiti -.-> Archivo

    Cerebro --> Oido
    Cerebro --> Habla
    Cerebro --> Hud
    CerebroSus --> Oido
    CerebroSus --> Habla
    CerebroSus --> Hud

    style MemoriaWIP stroke-dasharray: 5 5
    style PuertoMem stroke-dasharray: 5 5
```

## Notas de lectura

- **Líneas punteadas** = en construcción (memoria permanente) o dependencia
  opcional/condicional (login disparado solo si hace falta).
- **`Cerebro` vs `CerebroSuscripcion`**: dos implementaciones del mismo rol
  (conversar + ejecutar herramientas), elegidas en `__main__._crear_cerebro`
  según `Config.motor`. `CerebroSuscripcion` no pasa por el puerto
  `ProveedorIA` — usa el Claude Agent SDK directo, con las herramientas de
  Jarvis expuestas como servidor MCP embebido (mecanismo distinto, no un
  cliente HTTP intercambiable).
- **Nada de API keys manejadas por Jarvis** salvo `ANTHROPIC_API_KEY` si el
  usuario la puso directo en el entorno (comportamiento preexistente, sin
  menú). Claude (suscripción) y Codex usan sesión ya logueada en su CLI;
  Ollama no necesita clave.
- **Punto de extensión futuro** (decidido, no construido todavía): nuevas
  capacidades no deberían agregar un `.py` por feature — el plan es
  herramientas vía MCP externo + 1-2 herramientas genéricas (código/web),
  con el modelo eligiendo cuál usar según la tarea.
