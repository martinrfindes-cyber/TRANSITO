"""Verificación de referencias legales en las respuestas (anti-alucinación).

Regla del proyecto: el asistente solo puede citar fundamentos presentes en la
documentación recuperada. Este módulo extrae las referencias a "Artículo N" que
aparecen en la respuesta del modelo y comprueba que cada una esté respaldada por
el contexto recuperado. Las que no lo estén se marcan como NO verificadas.

Es una salvaguarda determinista y sin red: si el modelo inventa un artículo,
se detecta y se advierte al usuario.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .rag.articles import normalize_ref
from .rag.retriever import SearchResult

# Captura "artículo 50", "artículos 50, 51 y 52", "artículo 3 bis", etc.
_RE_ARTS = re.compile(
    r"art[íi]culos?\s+("
    r"\d+(?:\s*(?:bis|ter|qu[aá]ter|quintus|sexies|septies))?"
    r"(?:\s*(?:,|y|;|e)\s*\d+(?:\s*(?:bis|ter|qu[aá]ter))?)*"
    r")",
    re.IGNORECASE,
)
_RE_SINGLE = re.compile(
    r"\b(\d+)\s*(bis|ter|qu[aá]ter|quintus|sexies|septies)?",
    re.IGNORECASE,
)


def extract_article_refs(text: str) -> set[str]:
    """Devuelve el conjunto de referencias a artículos (normalizadas) del texto."""
    refs: set[str] = set()
    for run in _RE_ARTS.findall(text):
        for num, suf in _RE_SINGLE.findall(run):
            refs.add(normalize_ref(num, suf))
    return refs


@dataclass
class ValidationReport:
    """Resultado de verificar las referencias citadas en una respuesta."""

    cited: set[str] = field(default_factory=set)
    supported: set[str] = field(default_factory=set)
    unsupported: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not self.unsupported

    def note(self) -> str:
        """Nota legible para anexar a la respuesta si hay referencias sin respaldo."""
        if self.ok:
            return ""
        arts = ", ".join(sorted(self.unsupported, key=_sort_key))
        return (
            "\n\n> ⚠️ *Verificación de referencias:* no encontré respaldo en la "
            f"documentación recuperada para: artículo(s) {arts}. "
            "Trátalos con cautela y verifícalos directamente en el reglamento "
            "oficial antes de usarlos."
        )


def _sort_key(ref: str):
    m = re.match(r"(\d+)", ref)
    return (int(m.group(1)) if m else 0, ref)


def build_supported_refs(results: list[SearchResult]) -> set[str]:
    """Referencias a artículos presentes en el contexto recuperado (lo permitido)."""
    refs: set[str] = set()
    for r in results:
        # El encabezado del fragmento (p. ej. "Artículo 50") y su texto.
        refs |= extract_article_refs(r.chunk.heading)
        refs |= extract_article_refs(r.chunk.text)
    return refs


def validate_answer(
    answer: str, results: list[SearchResult]
) -> ValidationReport:
    """Comprueba que cada artículo citado en la respuesta esté en el contexto."""
    cited = extract_article_refs(answer)
    supported_universe = build_supported_refs(results)
    supported = {c for c in cited if c in supported_universe}
    unsupported = cited - supported
    return ValidationReport(
        cited=cited, supported=supported, unsupported=unsupported
    )
