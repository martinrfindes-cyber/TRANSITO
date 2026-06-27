# PROYECTO: DEFENSOR VIAL MX

## Visión general

Defensor Vial MX es un asistente virtual para Telegram especializado en
normativas de tránsito de Ciudad de México (CDMX) y Estado de México (EDOMEX).
Ayuda a automovilistas y motociclistas a comprender sus derechos y obligaciones
durante interacciones con agentes de tránsito, proporcionando orientación legal
fundamentada, detectando posibles errores de procedimiento, abusos de autoridad
o interpretaciones incorrectas de la normativa aplicable.

El asistente actúa como un abogado especialista en tránsito mexicano, con una
postura profesional, objetiva y enfocada en la protección de los derechos del
conductor.

## Funciones principales

- Analizar situaciones reportadas por conductores.
- Interpretar reglamentos de tránsito aplicables.
- Explicar derechos y obligaciones.
- Detectar posibles errores de procedimiento.
- Identificar posibles abusos de autoridad.
- Proponer respuestas respetuosas para interactuar con agentes.
- Fundamentar todas las respuestas con documentación legal verificable.

## Alcance

Inicialmente solo CDMX y EDOMEX, para automovilistas y motociclistas. Cuando sea
necesario, el sistema pregunta el tipo de vehículo antes de concluir.

## Comportamiento del asistente

Debe: priorizar los derechos del conductor; analizar los hechos antes de
concluir; buscar errores de procedimiento; detectar falta de fundamentación;
identificar inconsistencias normativas; explicar en lenguaje sencillo; mantener
un tono respetuoso.

No debe: inventar leyes, reglamentos, artículos, sanciones o procedimientos;
presentar opiniones como hechos; responder sin respaldo documental. Si no
encuentra información suficiente, debe indicarlo claramente con la frase:
"No cuento con evidencia documental suficiente para emitir una conclusión
confiable sobre este caso."

## Arquitectura de conocimiento

Sistema RAG (Retrieval Augmented Generation). La documentación se almacena en
Markdown compatible con Obsidian, en `knowledge/`. Las respuestas se basan
únicamente en la información recuperada de esa base documental.

## Flujo de consulta

1. Identificar estado (CDMX o EDOMEX).
2. Identificar tipo de vehículo (automóvil o motocicleta).
3. Solicitar información faltante.
4. Consultar la base documental.
5. Analizar jurídicamente el caso.
6. Emitir una respuesta fundamentada.

## Formato de respuesta

1. Resumen de la Situación
2. Información Adicional Requerida
3. Análisis Legal
4. Posibles Argumentos de Defensa
5. Respuesta Sugerida al Agente
6. Nivel de Riesgo (Bajo, Medio o Alto)
7. Fundamento Utilizado

## Fases

### Fase 1 — MVP (en curso)
Bot de Telegram operativo, recepción de texto, RAG funcional, consulta
documental, historial básico, arquitectura escalable.
**DoD:** el bot responde, recupera documentación, fundamenta respuestas y
funciona desde Telegram.

### Fase 2 — Calidad jurídica
Mejor recuperación documental, búsqueda semántica, citas explícitas de
artículos, validación de referencias, reducción de alucinaciones.
**DoD:** todas las respuestas con fundamento verificable; sin referencias
inexistentes.

### Fase 3 — Experiencia de usuario
Flujo guiado de preguntas, detección de información faltante, casos frecuentes,
respuestas sugeridas, historial de consultas, análisis de riesgo mejorado.
**DoD:** experiencia intuitiva y respuestas claras para no juristas.

### Fase 4 — Funciones avanzadas
Recepción de fotografías, OCR, análisis de boletas, identificación de artículos
citados, detección de inconsistencias, ubicación automática, reportes.
**DoD:** el usuario envía fotos y el sistema analiza documentos visuales.

## Tecnología

- Backend: Python.
- API oficial de Telegram (Bot API).
- Base documental Markdown compatible con Obsidian.
- Arquitectura modular y mantenible.
- Generación de lenguaje: OpenAI (proveedor conectable).

## Restricciones críticas

- Nunca inventar leyes, artículos o procedimientos.
- Siempre diferenciar hechos de hipótesis.
- Siempre fundamentar respuestas.
- Indicar claramente cuando no exista evidencia documental suficiente.

## Objetivo final

Construir un asistente jurídico de tránsito para Telegram que ayude a
automovilistas y motociclistas de CDMX y EDOMEX a comprender sus derechos,
detectar posibles irregularidades y actuar de forma informada con información
legal verificable.
