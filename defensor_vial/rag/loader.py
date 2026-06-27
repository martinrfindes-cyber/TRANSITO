"""Carga y fragmentación de la base de conocimiento en Markdown.

La base es compatible con Obsidian: cada archivo es un documento Markdown que
puede incluir frontmatter YAML sencillo (clave: valor) con metadatos como
``estado`` (CDMX / EDOMEX / AMBOS) y ``tema``.

El documento se divide en *chunks* siguiendo la jerarquía de encabezados
(``#``, ``##``, ``###`` ...). Cada chunk conserva la ruta de encabezados para
dar contexto al modelo y facilitar la cita del fundamento.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Estados soportados en Fase 1.
ESTADO_CDMX = "CDMX"
ESTADO_EDOMEX = "EDOMEX"
ESTADO_AMBOS = "AMBOS"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Chunk:
    """Fragmento recuperable de la base de conocimiento."""

    id: str
    source: str  # nombre de archivo, p. ej. "Reglamento-CDMX.md"
    title: str  # título del documento (primer H1 o nombre de archivo)
    heading_path: list[str]  # jerarquía de encabezados del fragmento
    text: str  # contenido del fragmento (sin el encabezado)
    estado: str = ESTADO_AMBOS  # CDMX | EDOMEX | AMBOS
    tema: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def heading(self) -> str:
        """Encabezado más específico del fragmento."""
        return self.heading_path[-1] if self.heading_path else self.title

    @property
    def citation(self) -> str:
        """Etiqueta legible para citar el origen del fragmento."""
        ruta = " › ".join(self.heading_path) if self.heading_path else self.title
        return f"{self.source} — {ruta}"

    def context_block(self) -> str:
        """Bloque de texto listo para inyectar en el prompt del LLM."""
        cabecera = self.citation
        return f"[FUENTE: {cabecera}] (estado: {self.estado})\n{self.text}".strip()


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Extrae frontmatter YAML simple (clave: valor) y devuelve (meta, cuerpo)."""
    meta: dict[str, str] = {}
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return meta, raw
    block = match.group(1)
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip().strip("'\"")
    body = raw[match.end():]
    return meta, body


def _infer_estado(filename: str, meta: dict[str, str]) -> str:
    """Determina el estado aplicable a partir de metadatos o nombre de archivo."""
    declared = (meta.get("estado") or "").upper().strip()
    if declared in {ESTADO_CDMX, ESTADO_EDOMEX, ESTADO_AMBOS}:
        return declared
    low = filename.lower()
    if "cdmx" in low:
        return ESTADO_CDMX
    if "edomex" in low or "estado-de-mexico" in low or "edo-mex" in low:
        return ESTADO_EDOMEX
    return ESTADO_AMBOS


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "seccion"


def _split_by_headings(body: str) -> list[tuple[list[str], str]]:
    """Divide el cuerpo en secciones (ruta_de_encabezados, texto)."""
    sections: list[tuple[list[str], str]] = []
    stack: list[tuple[int, str]] = []  # (nivel, texto del encabezado)
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        path = [h for _, h in stack]
        if text:
            sections.append((path, text))
        buffer.clear()

    for line in body.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            # Cerrar la sección acumulada antes de cambiar de encabezado.
            flush()
            level = len(m.group(1))
            heading = m.group(2).strip()
            # Ajustar la pila a la jerarquía actual.
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading))
        else:
            buffer.append(line)
    flush()
    return sections


def load_file(path: Path) -> list[Chunk]:
    """Carga un archivo Markdown y devuelve sus fragmentos."""
    raw = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    estado = _infer_estado(path.name, meta)
    tema = meta.get("tema", "")

    # Título: primer H1 si existe, si no el nombre de archivo sin extensión.
    title = path.stem
    for line in body.splitlines():
        m = _HEADING_RE.match(line)
        if m and len(m.group(1)) == 1:
            title = m.group(2).strip()
            break

    chunks: list[Chunk] = []
    sections = _split_by_headings(body)
    if not sections:
        text = body.strip()
        if text:
            sections = [([title], text)]

    for i, (heading_path, text) in enumerate(sections):
        if not heading_path:
            heading_path = [title]
        slug = _slugify("-".join(heading_path))
        chunk_id = f"{path.stem}#{i:03d}-{slug}"
        chunks.append(
            Chunk(
                id=chunk_id,
                source=path.name,
                title=title,
                heading_path=heading_path,
                text=text,
                estado=estado,
                tema=tema,
                metadata=meta,
            )
        )
    return chunks


def load_knowledge(knowledge_dir: Path) -> list[Chunk]:
    """Carga todos los ``.md`` de la carpeta de conocimiento (orden estable)."""
    knowledge_dir = Path(knowledge_dir)
    if not knowledge_dir.exists():
        raise FileNotFoundError(
            f"No existe la carpeta de conocimiento: {knowledge_dir}"
        )
    chunks: list[Chunk] = []
    for path in sorted(knowledge_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        chunks.extend(load_file(path))
    return chunks
