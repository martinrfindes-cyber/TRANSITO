"""Convierte un PDF de reglamento en un documento Markdown para la base RAG.

Extrae el texto con pdfplumber, limpia encabezados/pies de página repetidos y
estructura el contenido como Markdown (TÍTULO→H2, CAPÍTULO/SECCIÓN→H3,
Artículo→H4), de modo que cada artículo sea un fragmento recuperable y citable.

Uso:
    python scripts/pdf_to_knowledge.py ENTRADA.pdf SALIDA.md \
        --estado CDMX --titulo "Reglamento de Tránsito de la CDMX" \
        --fuente "Gaceta Oficial ..., última reforma ..."

Requiere: pip install pdfplumber
"""

from __future__ import annotations

import argparse
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

NOISE_EXACT = {
    "REGLAMENTO DE TRANSITO DEL ESTADO DE MEXICO",
    "REGLAMENTO DE TRÁNSITO DE LA CIUDAD DE MÉXICO",
    "DEL ESTADO DE MEXICO",
}
NOISE_PREFIX = (
    "Publicada en el Periódico Oficial",
    "Última reforma POGG",
    "PUBLICADO EN LA GACETA OFICIAL",
    "ÚLTIMA REFORMA PUBLICADA",
)

RE_TITULO = re.compile(r"^T[ÍI]TULO\b", re.IGNORECASE)
RE_CAPITULO = re.compile(r"^CAP[ÍI]TULO\b", re.IGNORECASE)
RE_SECCION = re.compile(r"^SECCI[ÓO]N\b", re.IGNORECASE)
RE_TRANSITORIOS = re.compile(r"^(ART[ÍI]CULOS\s+)?TRANSITORIOS?\b", re.IGNORECASE)
RE_ARTICULO = re.compile(
    r"^(Art[íi]culo\s+\d+(?:\s+(?:Bis|Ter|Qu[aá]ter|Quintus|Sexies|Septies))?)",
    re.IGNORECASE,
)
RE_PAGENUM = re.compile(r"^\d{1,4}$")


def is_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s in NOISE_EXACT or RE_PAGENUM.match(s):
        return True
    return any(s.startswith(p) for p in NOISE_PREFIX)


def extract_text(pdf_path: str) -> str:
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _name_on_next_line(lines, i, n):
    """Devuelve el nombre del encabezado si está en la línea siguiente."""
    nombre = lines[i + 1].strip() if i + 1 < n else ""
    if nombre and not (
        RE_TITULO.match(nombre) or RE_CAPITULO.match(nombre)
        or RE_SECCION.match(nombre) or RE_ARTICULO.match(nombre)
    ):
        return nombre
    return ""


def parse(raw: str) -> tuple[str, dict]:
    lines = [ln for ln in (l.rstrip() for l in raw.split("\n")) if not is_noise(ln)]
    out: list[str] = []
    stats = {"titulos": 0, "capitulos": 0, "secciones": 0, "articulos": 0}
    intro: list[str] = []
    started = False
    i, n = 0, len(lines)

    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        if RE_TITULO.match(line):
            if not started and intro:
                out += ["## Publicación y fundamento", ""] + intro + [""]
                intro = []
            started = True
            nombre = _name_on_next_line(lines, i, n)
            out += ["", f"## {line}" + (f" — {nombre}" if nombre else ""), ""]
            i += 2 if nombre else 1
            stats["titulos"] += 1
            continue

        for rx, mark, key in (
            (RE_CAPITULO, "###", "capitulos"),
            (RE_SECCION, "###", "secciones"),
        ):
            if rx.match(line):
                started = True
                nombre = _name_on_next_line(lines, i, n)
                out += ["", f"{mark} {line}" + (f" — {nombre}" if nombre else ""), ""]
                i += 2 if nombre else 1
                stats[key] += 1
                break
        else:
            if RE_TRANSITORIOS.match(line):
                started = True
                out += ["", f"## {line}", ""]
                i += 1
                continue
            m = RE_ARTICULO.match(line)
            if m:
                started = True
                out += ["", f"#### {m.group(1).strip()}", "", line]
                i += 1
                stats["articulos"] += 1
                continue
            (out if started else intro).append(line)
            i += 1
            continue
        continue

    if intro and not started:
        out += intro

    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
    return text, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf")
    ap.add_argument("out")
    ap.add_argument("--estado", required=True, choices=["CDMX", "EDOMEX", "AMBOS"])
    ap.add_argument("--titulo", required=True)
    ap.add_argument("--fuente", default="")
    ap.add_argument("--tema", default="")
    args = ap.parse_args()

    raw = extract_text(args.pdf)
    body, stats = parse(raw)
    fm = (
        "---\n"
        f"estado: {args.estado}\n"
        f"tema: {args.tema or args.titulo}\n"
        f"fuente: {args.fuente}\n"
        "verificado: verificado\n"
        "---\n\n"
        f"# {args.titulo}\n\n"
        "> Texto oficial. Cada artículo aparece bajo su Título y Capítulo.\n"
        "> Citar siempre el número de artículo tal como aparece aquí.\n\n"
    )
    open(args.out, "w", encoding="utf-8").write(fm + body)
    print(f"{args.pdf} -> {args.out}")
    print(" ", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
