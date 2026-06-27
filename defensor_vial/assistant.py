"""Orquestación del flujo de atención de Defensor Vial MX.

Implementa el FLUJO GENERAL DE ATENCIÓN de la Fase 1:
1. Identificar estado (CDMX / EDOMEX).
2. Identificar tipo de vehículo (automóvil / motocicleta).
3. Recuperar documentación relevante (RAG, filtrada por estado).
4. Construir el prompt y generar la respuesta fundamentada con el LLM.
5. Mantener historial básico de conversación.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Config
from .history import SessionStore
from .llm import build_llm
from .llm.base import LLMClient, LLMError, Message
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .rag.articles import ArticleIndex
from .rag.loader import ESTADO_CDMX, ESTADO_EDOMEX, load_knowledge
from .rag.retriever import BM25Retriever, SearchResult, strip_accents
from .validation import (
    ValidationReport,
    build_supported_refs,
    extract_article_refs,
    validate_answer,
)

# --- Heurísticas de detección (ligeras; el LLM también pide datos faltantes) ---

_CDMX_PATTERNS = [
    r"\bcdmx\b", r"ciudad de mexico", r"\bdf\b", r"\bd\.f\.?\b",
    r"distrito federal",
]
_EDOMEX_PATTERNS = [
    r"\bedomex\b", r"estado de mexico", r"edo\.? de mex", r"edo mex",
    r"\bnaucalpan\b", r"\bnezahualcoyotl\b", r"\bneza\b", r"\becatepec\b",
    r"\btlalnepantla\b", r"\btoluca\b", r"\bcuautitlan\b", r"\bchalco\b",
    r"\btecamac\b", r"\bmetepec\b", r"\bhuixquilucan\b", r"\bcoacalco\b",
]
_MOTO_PATTERNS = [
    r"\bmoto\b", r"\bmotos\b", r"motociclet", r"\bmotociclista\b", r"\bscooter\b",
    r"\bcasco\b",
]
_AUTO_PATTERNS = [
    r"\bauto\b", r"\bautomovil\b", r"\bautomóvil\b", r"\bcoche\b", r"\bcarro\b",
    r"\bvehiculo\b", r"\bcamioneta\b", r"\bsedan\b",
]


def _match_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def _ref_sort_key(ref: str):
    """Ordena referencias de artículo por número y luego por sufijo (bis, ter)."""
    m = re.match(r"(\d+)", ref)
    return (int(m.group(1)) if m else 0, ref)


def detect_estado(text: str) -> str | None:
    """Detecta CDMX o EDOMEX en el texto. Devuelve None si es ambiguo."""
    norm = strip_accents(text.lower())
    cdmx = _match_any(_CDMX_PATTERNS, norm)
    edomex = _match_any(_EDOMEX_PATTERNS, norm)
    if cdmx and not edomex:
        return ESTADO_CDMX
    if edomex and not cdmx:
        return ESTADO_EDOMEX
    return None


def detect_vehiculo(text: str) -> str | None:
    """Detecta tipo de vehículo (motocicleta / automovil). None si ambiguo."""
    norm = strip_accents(text.lower())
    moto = _match_any(_MOTO_PATTERNS, norm)
    auto = _match_any(_AUTO_PATTERNS, norm)
    if moto and not auto:
        return "motocicleta"
    if auto and not moto:
        return "automovil"
    return None


@dataclass
class AssistantReply:
    """Respuesta del asistente más metadatos útiles para depurar."""

    text: str
    estado: str | None
    vehiculo: str | None
    results: list[SearchResult]
    used_llm: bool
    validation: ValidationReport | None = None


class Assistant:
    """Punto de entrada principal del asistente (independiente de Telegram)."""

    def __init__(
        self,
        config: Config,
        retriever: BM25Retriever | None = None,
        llm: LLMClient | None = None,
        sessions: SessionStore | None = None,
    ):
        self.config = config
        self.retriever = retriever or BM25Retriever(
            load_knowledge(config.knowledge_dir)
        )
        self._llm = llm
        self.sessions = sessions or SessionStore()
        self.articles = ArticleIndex.from_chunks(self.retriever.chunks)

    @property
    def llm(self) -> LLMClient:
        # Construcción perezosa: permite probar la recuperación sin API key.
        if self._llm is None:
            self._llm = build_llm(self.config)
        return self._llm

    def retrieve(
        self, query: str, estado: str | None
    ) -> list[SearchResult]:
        """Recupera fragmentos relevantes y aplica el umbral mínimo.

        Si el usuario menciona un artículo concreto (p. ej. "artículo 50"), se
        recupera ese artículo de forma directa y se coloca al frente.
        """
        results = self.retriever.search(
            query, top_k=self.config.top_k, estado=estado
        )
        results = [r for r in results if r.score >= self.config.min_score]
        return self._inject_explicit_articles(query, estado, results)

    def _inject_explicit_articles(
        self, query: str, estado: str | None, results: list[SearchResult]
    ) -> list[SearchResult]:
        """Añade al frente los artículos citados explícitamente en la consulta."""
        refs = extract_article_refs(query)
        if not refs:
            return results
        estados = [estado] if estado else [ESTADO_CDMX, ESTADO_EDOMEX]
        existentes = {r.chunk.id for r in results}
        directos: list[SearchResult] = []
        for ref in refs:
            for est in estados:
                chunk = self.articles.get(est, ref)
                if chunk and chunk.id not in existentes:
                    directos.append(SearchResult(chunk=chunk, score=1.0))
                    existentes.add(chunk.id)
        return directos + results

    def answer(self, user_id: str, message: str) -> AssistantReply:
        """Procesa un mensaje del usuario y devuelve la respuesta del asistente."""
        session = self.sessions.get(user_id)

        # 1-2. Identificar estado y vehículo (recordando lo ya conocido).
        estado = detect_estado(message) or session.estado
        vehiculo = detect_vehiculo(message) or session.vehiculo
        session.estado = estado
        session.vehiculo = vehiculo

        # 3. Recuperación documental con contexto conversacional. Se combinan los
        # últimos mensajes del usuario con el actual para no perder el tema
        # cuando un mensaje de seguimiento solo aporta un dato suelto
        # (p. ej. "Fue en la Ciudad de México").
        prior_user = [m.content for m in session.turns if m.role == "user"][-2:]
        retrieval_query = " ".join([*prior_user, message]).strip()
        results = self.retrieve(retrieval_query, estado)

        # 4. Construcción de mensajes y generación.
        available = sorted(build_supported_refs(results), key=_ref_sort_key)
        user_prompt = build_user_prompt(
            message, results, estado, vehiculo, available_refs=available
        )
        messages: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]
        messages.extend(session.recent(self.config.history_max_turns))
        messages.append(Message(role="user", content=user_prompt))

        text = self.llm.complete(messages)

        # 5. Verificación de referencias: si el modelo citó un artículo sin
        # respaldo en el contexto recuperado, se anexa una advertencia.
        report = validate_answer(text, results)
        if not report.ok:
            text = text + report.note()

        # 6. Historial: se guarda el mensaje original del usuario (no el prompt
        # enriquecido) y la respuesta, para conservar contexto legible.
        session.add("user", message)
        session.add("assistant", text)

        return AssistantReply(
            text=text,
            estado=estado,
            vehiculo=vehiculo,
            results=results,
            used_llm=True,
            validation=report,
        )

    def reset(self, user_id: str) -> None:
        self.sessions.reset(user_id)
