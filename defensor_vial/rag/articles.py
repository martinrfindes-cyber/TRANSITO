"""Índice de artículos de los reglamentos cargados.

Permite (a) localizar un artículo concreto por número y estado para recuperarlo
directamente cuando el usuario lo menciona, y (b) conocer el conjunto de
artículos realmente existentes, base para la verificación de referencias.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .loader import Chunk

# "Artículo 50", "Artículo 3 Bis", "ARTÍCULO 12 Ter", etc.
_RE_ART_HEADING = re.compile(
    r"art[íi]culo\s+(\d+)\s*(bis|ter|qu[aá]ter|quintus|sexies|septies)?",
    re.IGNORECASE,
)


def normalize_ref(numero: str, sufijo: str | None = None) -> str:
    """Normaliza una referencia a artículo: '3', 'bis' -> '3 bis'."""
    numero = numero.strip()
    suf = (sufijo or "").strip().lower()
    suf = suf.replace("á", "a")  # 'quáter' -> 'quater'
    return f"{numero} {suf}".strip() if suf else numero


@dataclass
class ArticleIndex:
    """Mapa (estado, ref_normalizada) -> Chunk del artículo."""

    by_key: dict[tuple[str, str], Chunk] = field(default_factory=dict)

    @classmethod
    def from_chunks(cls, chunks: list[Chunk]) -> "ArticleIndex":
        idx = cls()
        for c in chunks:
            m = _RE_ART_HEADING.match(c.heading.strip())
            if not m:
                continue
            ref = normalize_ref(m.group(1), m.group(2))
            idx.by_key[(c.estado, ref)] = c
        return idx

    def get(self, estado: str, ref: str) -> Chunk | None:
        return self.by_key.get((estado, ref.lower().strip()))

    def exists(self, estado: str, ref: str) -> bool:
        return (estado, ref.lower().strip()) in self.by_key

    def refs_for_estado(self, estado: str) -> set[str]:
        return {ref for (est, ref) in self.by_key if est == estado}

    def count(self, estado: str | None = None) -> int:
        if estado is None:
            return len(self.by_key)
        return sum(1 for (est, _) in self.by_key if est == estado)
