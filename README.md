# ⚖️ Defensor Vial MX

Asistente jurídico de tránsito para **Telegram**, especializado en **Ciudad de
México (CDMX)** y **Estado de México (EDOMEX)**. Ayuda a automovilistas y
motociclistas a entender sus derechos, identificar posibles irregularidades en
procedimientos de tránsito y actuar de forma informada, **fundamentando siempre
sus respuestas en documentación verificable** (RAG).

> Estado del proyecto: **Fase 2 — Calidad jurídica (en curso).** Fase 1 ✅

---

## ✨ Qué hace (Fase 1)

- Bot de Telegram operativo (recepción de mensajes de texto).
- Sistema **RAG** (Retrieval Augmented Generation) con base documental en
  Markdown compatible con Obsidian.
- Identificación automática de **estado** (CDMX/EDOMEX) y **tipo de vehículo**.
- Recuperación documental filtrada por estado.
- Respuesta con el **formato jurídico obligatorio** (resumen, análisis,
  argumentos de defensa, respuesta sugerida, nivel de riesgo, fundamento).
- **Historial básico** de conversación por usuario.
- Restricción crítica aplicada: **nunca inventa leyes ni artículos**; si falta
  evidencia documental, lo declara explícitamente.

---

## 🏗️ Arquitectura

```
TRANSITO/
├── main.py                 # Punto de entrada (bot / CLI / utilidades)
├── requirements.txt
├── .env.example            # Plantilla de configuración
├── docs/proyecto.md        # Especificación del proyecto
├── knowledge/              # Base documental RAG (Markdown / Obsidian)
│   ├── Reglamento-CDMX.md, Reglamento-Edomex.md, ...
│   └── README.md           # Cómo poblar la base con texto oficial
├── defensor_vial/          # Paquete principal
│   ├── config.py           # Configuración por variables de entorno
│   ├── prompts.py          # Persona, restricciones y formato de respuesta
│   ├── assistant.py        # Orquestación del flujo de atención
│   ├── history.py          # Historial y estado de sesión (en memoria)
│   ├── bot.py              # Cliente de Telegram (long polling, stdlib)
│   ├── rag/                # loader (chunking) + retriever (BM25 puro)
│   └── llm/                # Capa de LLM conectable (OpenAI por defecto)
└── tests/test_rag.py       # Pruebas del RAG y heurísticas
```

**Decisiones de diseño (priorizando estabilidad):**

- **RAG con BM25 en Python puro** (sin numpy ni modelos): determinista, offline
  y fácil de auditar — clave para la exactitud jurídica. En Fase 2 se puede
  añadir búsqueda semántica (embeddings).
- **Telegram y OpenAI vía `urllib`** (librería estándar): sin dependencias con
  extensiones compiladas, máxima compatibilidad con Python 3.14 en Windows.
- **Proveedor de LLM conectable**: hoy OpenAI; añadir otro no afecta el resto.

---

## 🚀 Puesta en marcha

### 1. Requisitos

- Python 3.10+ (probado en 3.14).
- Una **clave de API de OpenAI** y un **token de bot de Telegram**.

### 2. Instalación

```powershell
# (opcional pero recomendado) entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 3. Configuración

Copia `.env.example` como `.env` y completa:

```
TELEGRAM_BOT_TOKEN=...        # de @BotFather en Telegram
OPENAI_API_KEY=...            # de https://platform.openai.com/api-keys
OPENAI_MODEL=gpt-4o-mini      # o gpt-4o para mayor precisión
```

### 4. Verificar la instalación (sin gastar API)

```powershell
python main.py --check
python main.py --retrieve "En CDMX me quieren multar por polarizado" -v
python tests\test_rag.py
```

### 5. Probar en consola (requiere OPENAI_API_KEY)

```powershell
python main.py --cli
```

### 6. Arrancar el bot de Telegram

```powershell
python main.py
```

Abre tu bot en Telegram y envía `/start`.

---

## 🤖 Comandos del bot

- `/start` — bienvenida y ejemplo de uso.
- `/help` — ayuda y alcance.
- `/reset` — reinicia el historial y los datos de la sesión.
- Cualquier otro texto se analiza como una consulta.

---

## 📚 La base de conocimiento (importante)

El asistente **solo** fundamenta con lo que está en `knowledge/`. Ya están
cargados los **textos oficiales completos**:

- **Reglamento de Tránsito de la CDMX** (72 artículos + transitorios).
- **Reglamento de Tránsito del Estado de México** (155 artículos).

Cada artículo es un fragmento independiente, citable por su número y ubicado
bajo su Título/Capítulo originales. Los archivos temáticos complementan con el
marco de análisis. El asistente nunca inventa artículos; si falta un dato, lo
declara. El índice se reconstruye al iniciar (no hay que reindexar).

### Agregar otro reglamento (p. ej. municipal)

```powershell
python scripts\pdf_to_knowledge.py "ruta\al.pdf" knowledge\Mi-Reglamento.md `
    --estado EDOMEX --titulo "Reglamento de Tránsito de <Municipio>" `
    --fuente "Gaceta ..., última reforma ..."
```

El script extrae el texto, limpia encabezados de página y estructura
TÍTULO/CAPÍTULO/Artículo automáticamente. Requiere `pip install pdfplumber`.

### Puente de vocabulario (recuperación)

Como los reglamentos usan términos técnicos ("alcohol", "cristales") distintos a
los coloquiales ("alcoholímetro", "polarizado"), el recuperador expande la
consulta con un pequeño mapa de sinónimos del dominio
([`retriever.py`](defensor_vial/rag/retriever.py)) para mejorar el *recall* sin
alterar el contenido. La búsqueda semántica plena (embeddings) es Fase 2.

---

## ⚙️ Variables de entorno

| Variable | Descripción | Default |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token del bot | — |
| `LLM_PROVIDER` | Proveedor de LLM | `openai` |
| `OPENAI_API_KEY` | Clave de OpenAI | — |
| `OPENAI_MODEL` | Modelo | `gpt-4o-mini` |
| `LLM_TEMPERATURE` | Temperatura | `0.2` |
| `KNOWLEDGE_DIR` | Carpeta de la base | `./knowledge` |
| `RAG_TOP_K` | Fragmentos a recuperar | `6` |
| `RAG_MIN_SCORE` | Umbral de evidencia | `0.05` |
| `HISTORY_MAX_TURNS` | Mensajes de historial | `8` |

---

## ✅ Definition of Done — Fase 1

| Requisito | Estado |
|---|---|
| Bot de Telegram operativo | ✅ Cliente long polling (API oficial) |
| Recepción de mensajes de texto | ✅ |
| Sistema RAG funcional | ✅ BM25 + chunking por encabezados |
| Consulta documental | ✅ Filtrada por estado |
| Identificación CDMX / EDOMEX | ✅ Heurística + metadatos |
| Historial básico | ✅ Sesión por usuario en memoria |
| Arquitectura limpia y escalable | ✅ Módulos desacoplados, LLM conectable |
| Fundamenta respuestas | ✅ Solo con documentación recuperada |

> El único paso que requiere credenciales del usuario es la llamada real al LLM
> y a Telegram. Todo lo demás está validado con pruebas automáticas.

---

## 🧪 Fase 2 — Calidad jurídica

| Requisito | Estado |
|---|---|
| Reglamentos oficiales cargados | ✅ CDMX (70 arts) + EDOMEX (145 arts) |
| Mejor recuperación documental | ✅ sinónimos + búsqueda directa por artículo |
| Citas explícitas de artículos | ✅ se entrega al modelo la lista de artículos válidos |
| **Verificación de referencias** | ✅ se valida cada "Artículo N" citado contra el contexto |
| **Reducción de alucinaciones** | ✅ artículos sin respaldo se marcan automáticamente |
| Búsqueda semántica (embeddings) | ⏳ siguiente paso (requiere `OPENAI_API_KEY`) |

**Verificación de referencias (anti-alucinación):** tras generar la respuesta,
[`validation.py`](defensor_vial/validation.py) extrae cada artículo citado y
comprueba que esté en la documentación recuperada. Si el modelo cita un artículo
inexistente o sin respaldo, se anexa una advertencia visible al usuario. Es una
salvaguarda **determinista y sin red**.

## 🗺️ Próximas fases

- **Fase 2 (cierre):** búsqueda semántica con embeddings de OpenAI + caché.
- **Fase 3 — Experiencia de usuario:** flujo guiado, casos frecuentes,
  detección de información faltante.
- **Fase 4 — Funciones avanzadas:** fotos, OCR de boletas, ubicación automática.

---

## ⚠️ Aviso legal

Defensor Vial MX ofrece **orientación informativa** basada en documentación y
**no sustituye la asesoría de un abogado**. La precisión jurídica depende de que
la base de conocimiento contenga el texto oficial vigente.
