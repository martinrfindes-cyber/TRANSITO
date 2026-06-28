"""Recuperador BM25 en Python puro (sin dependencias externas).

BM25 es un algoritmo de ranking probabilístico clásico y robusto para
recuperación léxica. Se eligió para el MVP porque:
- No requiere modelos pesados ni llamadas externas (funciona offline).
- Es determinista y fácil de depurar — clave para "exactitud jurídica".
- En Fase 2 puede sustituirse/combinarse con búsqueda semántica (embeddings).

El recuperador soporta filtrado por estado (CDMX / EDOMEX), de modo que una
consulta marcada para CDMX no recupere fundamentos del EDOMEX y viceversa.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from .loader import ESTADO_AMBOS, Chunk

# Palabras vacías en español que aportan poco a la recuperación léxica.
_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
    "a", "ante", "con", "en", "para", "por", "que", "se", "su", "sus", "y", "o",
    "u", "e", "lo", "le", "les", "me", "mi", "te", "tu", "es", "son", "fue",
    "ser", "estar", "este", "esta", "esto", "ese", "esa", "eso", "como", "mas",
    "pero", "si", "no", "ya", "muy", "sin", "sobre", "tambien", "hay", "han",
    "he", "ha", "soy", "eres", "del", "cuando", "donde", "porque", "cual",
    "cuales", "yo", "el", "ellos", "ellas", "nos", "vos", "usted", "ustedes",
}

_TOKEN_RE = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)

# Puente de vocabulario ciudadano -> vocabulario legal (tokens sin acento).
# Los reglamentos usan términos técnicos ("alcohol", "cristales") que difieren
# de cómo la gente describe su caso ("alcoholímetro", "polarizado"). Esta tabla
# expande la consulta para mejorar la *recuperación* (recall); NO modifica el
# texto recuperado ni inventa contenido. La búsqueda semántica plena es Fase 2.
SYNONYMS: dict[str, list[str]] = {
    "alcoholimetro": ["alcohol", "aliento", "embriaguez", "narcoticos"],
    "alcoholemia": ["alcohol", "embriaguez"],
    "ebrio": ["alcohol", "embriaguez"],
    "borracho": ["alcohol", "embriaguez"],
    "polarizado": ["cristales", "oscurecer", "vidrios", "transparencia", "parabrisas"],
    "polarizada": ["cristales", "oscurecer", "vidrios", "transparencia"],
    "polarizados": ["cristales", "oscurecer", "vidrios", "transparencia"],
    "polarizar": ["cristales", "oscurecer", "vidrios"],
    "filtrado": ["carril", "carriles", "circular", "motocicleta"],
    "filtrar": ["carril", "carriles", "circular"],
    "corralon": ["deposito", "arrastre", "grua", "retira", "remitir"],
    "grua": ["deposito", "arrastre", "retira"],
    "deposito": ["arrastre", "retira", "remitir"],
    "moto": ["motocicleta"],
    "motos": ["motocicleta"],
    "casco": ["casco", "proteccion"],
    "multa": ["sancion", "infraccion", "boleta"],
    "multar": ["sancion", "infraccion", "boleta"],
    "multaron": ["sancion", "infraccion", "boleta"],
    "placas": ["placa", "matricula"],
    "licencia": ["licencia", "permiso", "conducir"],
    "verificacion": ["verificacion", "emisiones", "holograma", "contaminantes"],
    "verificar": ["verificacion", "emisiones", "holograma"],
    "celular": ["telefono", "dispositivo", "manos"],
    "telefono": ["celular", "dispositivo"],
    "exceso": ["velocidad", "maxima", "limite"],
    "velocidad": ["velocidad", "maxima", "limite"],
    "ciclovia": ["ciclista", "ciclistas", "ciclocarril"],
    "ciclovias": ["ciclista", "ciclistas", "ciclocarril"],
    "estacionada": ["estacionar", "estacionamiento"],
    "estacionado": ["estacionar", "estacionamiento"],
    "estacione": ["estacionar", "estacionamiento"],
    "estacionarse": ["estacionar", "estacionamiento"],
    "estacionar": ["estacionamiento"],
    "banqueta": ["peatonal", "acera", "peatones"],
    "banquetas": ["peatonal", "acera", "peatones"],
    # Derechos del conductor / detención / revisión / actuación de la autoridad.
    # La gente describe la situación coloquialmente ("me paró un poli por
    # sospechoso") mientras la guía usa términos constitucionales ("molestado",
    # "detención", "fundamentación", "legalidad").
    "sospechoso": ["detencion", "molestado", "legalidad", "fundamentacion"],
    "sospecha": ["detencion", "molestado", "legalidad"],
    "sospechosa": ["detencion", "molestado", "legalidad"],
    "poli": ["agente", "autoridad", "transito"],
    "policia": ["agente", "autoridad"],
    "tira": ["agente", "autoridad"],
    "detuvo": ["detencion", "molestado", "senalamiento"],
    "detuvieron": ["detencion", "molestado", "senalamiento"],
    "detener": ["detencion", "molestado"],
    "paro": ["detencion", "molestado", "senalamiento"],
    "pararon": ["detencion", "molestado", "senalamiento"],
    "parar": ["detencion", "molestado"],
    "detenido": ["detencion", "molestado"],
    "revisar": ["detencion", "molestado", "legalidad", "registro"],
    "revision": ["detencion", "molestado", "legalidad", "registro"],
    "revisaron": ["detencion", "molestado", "legalidad"],
    "registro": ["detencion", "molestado", "legalidad"],
    "registrar": ["detencion", "molestado", "legalidad"],
    "carro": ["vehiculo"],
    "coche": ["vehiculo"],
    "auto": ["vehiculo"],
    "derechos": ["legalidad", "debido", "proceso", "fundamentacion", "impugnar"],
    "derecho": ["legalidad", "debido", "proceso"],
    "puede": ["legalidad", "fundamentacion", "facultad"],
    "pueden": ["legalidad", "fundamentacion", "facultad"],
    "abuso": ["legalidad", "molestado", "impugnar"],
    "abusar": ["legalidad", "molestado", "impugnar"],
    "ilegal": ["legalidad", "molestado", "impugnar"],
    "arbitrario": ["legalidad", "molestado", "impugnar"],
    "injusto": ["legalidad", "impugnar", "molestado"],
    "corrupto": ["cohecho", "dadivas", "impugnar"],
    "mordida": ["cohecho", "dadivas"],
    "soborno": ["cohecho", "dadivas"],
    "identificar": ["identificacion", "gafete", "agente"],
    "identificarse": ["identificacion", "gafete", "agente"],
    "gafete": ["identificacion", "agente"],
    "impugnar": ["impugnar", "legalidad", "debido"],
    "inconforme": ["impugnar", "legalidad"],
    "queja": ["impugnar", "legalidad"],
    "boleta": ["boleta", "infraccion", "fundamentacion", "motivacion"],
}


def strip_accents(text: str) -> str:
    """Elimina diacríticos para que 'multó' y 'multo' coincidan."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    """Normaliza, separa en tokens y elimina palabras vacías."""
    text = strip_accents(text.lower())
    tokens = _TOKEN_RE.findall(text)
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def expand_query(tokens: list[str]) -> list[str]:
    """Añade sinónimos legales a los tokens de la consulta (mejora el recall)."""
    expanded = list(tokens)
    for tok in tokens:
        for syn in SYNONYMS.get(tok, ()):  # type: ignore[arg-type]
            if syn not in expanded:
                expanded.append(syn)
    return expanded


@dataclass
class SearchResult:
    """Resultado de una búsqueda: fragmento + puntaje normalizado [0, 1]."""

    chunk: Chunk
    score: float


class BM25Retriever:
    """Índice BM25 sobre una lista de :class:`Chunk`."""

    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self._doc_tokens: list[list[str]] = []
        self._doc_freqs: list[dict[str, int]] = []
        self._doc_len: list[int] = []
        self._df: dict[str, int] = {}
        self._idf: dict[str, float] = {}
        self._avgdl: float = 0.0
        self._build()

    def _build(self) -> None:
        for chunk in self.chunks:
            # Se indexa el texto junto con la ruta de encabezados y el tema,
            # de modo que el título de la sección también pese en la búsqueda.
            indexable = " ".join(
                [" ".join(chunk.heading_path), chunk.tema, chunk.text]
            )
            tokens = tokenize(indexable)
            freqs: dict[str, int] = {}
            for tok in tokens:
                freqs[tok] = freqs.get(tok, 0) + 1
            self._doc_tokens.append(tokens)
            self._doc_freqs.append(freqs)
            self._doc_len.append(len(tokens))
            for tok in freqs:
                self._df[tok] = self._df.get(tok, 0) + 1

        n = len(self.chunks)
        self._avgdl = (sum(self._doc_len) / n) if n else 0.0
        # IDF de BM25 (variante con suavizado, siempre positiva).
        for tok, df in self._df.items():
            self._idf[tok] = math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _score(self, query_tokens: list[str], idx: int) -> float:
        freqs = self._doc_freqs[idx]
        dl = self._doc_len[idx]
        score = 0.0
        for tok in query_tokens:
            f = freqs.get(tok, 0)
            if f == 0:
                continue
            idf = self._idf.get(tok, 0.0)
            denom = f + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1))
            score += idf * (f * (self.k1 + 1)) / denom
        return score

    def search(
        self,
        query: str,
        top_k: int = 6,
        estado: str | None = None,
    ) -> list[SearchResult]:
        """Recupera los ``top_k`` fragmentos más relevantes.

        Si se indica ``estado`` (CDMX/EDOMEX), solo se consideran fragmentos de
        ese estado o marcados como AMBOS.
        """
        query_tokens = expand_query(tokenize(query))
        if not query_tokens:
            return []

        raw_scores: list[tuple[int, float]] = []
        for idx, chunk in enumerate(self.chunks):
            if estado and chunk.estado not in {estado, ESTADO_AMBOS}:
                continue
            s = self._score(query_tokens, idx)
            if s > 0:
                raw_scores.append((idx, s))

        if not raw_scores:
            return []

        # Normaliza a [0, 1] respecto al mejor puntaje de esta consulta para
        # poder aplicar un umbral de "evidencia suficiente" estable.
        max_score = max(s for _, s in raw_scores)
        raw_scores.sort(key=lambda x: x[1], reverse=True)
        results = [
            SearchResult(chunk=self.chunks[idx], score=s / max_score)
            for idx, s in raw_scores[:top_k]
        ]
        return results
