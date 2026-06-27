# Base de conocimiento — Defensor Vial MX

Esta carpeta es la **base documental RAG** del asistente y es compatible con
Obsidian (puedes abrir esta carpeta como un *vault*).

## Cómo funciona

- Cada archivo `.md` es un documento. Se divide en fragmentos por sus
  encabezados (`#`, `##`, `###`) y cada fragmento se indexa para búsqueda.
- El **frontmatter** YAML al inicio de cada archivo define metadatos:
  - `estado`: `CDMX`, `EDOMEX` o `AMBOS` (filtra la recuperación por estado).
  - `tema`: descripción corta del contenido.
  - `verificado`: `pendiente`, `parcial` o `verificado`.
- El asistente **solo** puede fundamentar con lo que esté en estos archivos.

## Estado actual

- ✅ **`Reglamento-CDMX.md`** — texto oficial completo (Gaceta Oficial
  17/08/2015, última reforma 06/05/2026). 72 artículos + transitorios.
- ✅ **`Reglamento-Edomex.md`** — texto oficial completo (Gaceta del Gobierno
  21/09/1992, última reforma POGG 10/11/2025). 155 artículos.
- Cada artículo está bajo su Título y Capítulo originales, como fragmento
  recuperable y citable (p. ej. *"… › Artículo 50"*).
- Los archivos temáticos (`Polarizados.md`, `Alcoholimetro.md`, etc.) aportan el
  **marco de análisis** y enlazan con los artículos. Donde citan principios
  constitucionales (arts. 14 y 16) son verificables; donde aún falta un dato
  específico mantienen `⚠️ VERIFICAR Y COMPLETAR`.

> El asistente solo afirma como fundamento lo que está en estos archivos. Para
> incorporar otro reglamento (p. ej. municipal del EDOMEX), usa el script
> `scripts/pdf_to_knowledge.py` (ver README principal).

## Cómo agregar/actualizar contenido oficial

1. Edita el archivo correspondiente (p. ej. `Reglamento-CDMX.md`).
2. Pega el articulado oficial bajo encabezados temáticos `##`/`###`.
3. Conserva el número de artículo exacto dentro del texto.
4. Cuando un documento quede respaldado, cambia `verificado: verificado`.
5. No es necesario reindexar manualmente: el índice se construye al iniciar.

## Archivos

- `Reglamento-CDMX.md`, `Reglamento-Edomex.md` — articulado base por estado.
- `Derechos-del-conductor.md` — principios constitucionales.
- `Procedimiento-de-infraccion.md` — procedimiento y errores a revisar.
- `Licencias.md`, `Verificacion.md`, `Polarizados.md`, `Alcoholimetro.md`.
- `Motocicletas-CDMX.md`, `Motocicletas-Edomex.md`, `Cascos.md`,
  `Filtrado-carriles.md`, `Retencion-motocicleta.md`, `Retencion-documentos.md`.
- `Casos-frecuentes.md` — guía rápida de encuadre.
